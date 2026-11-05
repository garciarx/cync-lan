"""Bridge choice for a burst of commands (an HA light group of 5 rooms fires 5 commands at once).

A bridge relays control packets into the BLE mesh one at a time. Hardware (2026-11-05, Master tile): the same 2 bridges
for all 5 rooms, in one write each (CYNC_CMD_BATCH_MS), made the stagger worse and 2 rooms never switched. So:
- a group command goes first through a bridge that is a member of that group (it is in the room and acts itself);
- the other slots go to the bridges that were used least recently, so a burst is spread over as many bridges as exist.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cync_lan.devices import device as device_mod
from cync_lan.devices.group import CyncGroup
from cync_lan.devices.session import CyncTCPSession

HOME = 1754061898


def bridge(name):
    s = CyncTCPSession.__new__(CyncTCPSession)
    s.ip_address = name
    s.lp = name + ":"
    s.ready_to_control = True
    s.mitm_mode = False
    s.queue_id = b"\x00\x00\x00\x01"
    s.node = SimpleNamespace(id=1)
    s.messages = SimpleNamespace(control={})
    s.write = AsyncMock(return_value=True)
    counter = iter(range(1, 255))
    s.get_ctrl_msg_id_bytes = lambda: [next(counter)]
    return s


def setup(monkeypatch, n):
    monkeypatch.setattr(device_mod, "CYNC_CMD_BROADCASTS", 2)
    pool = [bridge(f"10.0.0.{i}") for i in range(1, n + 1)]
    monkeypatch.setattr(device_mod.g, "ncync_server", SimpleNamespace(get_dev_tcp_pool=AsyncMock(return_value=pool)))
    monkeypatch.setattr(device_mod.g, "mqtt_client", SimpleNamespace(update_entity_power=AsyncMock()))
    return pool


async def test_a_burst_of_five_rooms_uses_ten_different_bridges(monkeypatch):
    pool = setup(monkeypatch, 10)
    for gid in (0x13, 0x15, 0x0B, 0x0A, 0x08):
        await CyncGroup(HOME, 0x8000 + gid, "room", []).set_power(1)
    assert [b.write.await_count for b in pool] == [1] * 10


async def test_with_fewer_bridges_the_load_is_even(monkeypatch):
    pool = setup(monkeypatch, 4)
    for gid in (0x13, 0x15, 0x0B, 0x0A, 0x08, 0x09):
        await CyncGroup(HOME, 0x8000 + gid, "room", []).set_power(1)
    assert sorted(b.write.await_count for b in pool) == [3, 3, 3, 3]


async def test_a_group_goes_through_a_member_bridge_first(monkeypatch):
    pool = setup(monkeypatch, 6)
    member = device_mod.CyncDevice(23, dev_type=53, name="sw", home_id=HOME, home_name="H", entities={})
    member.tcp_session = pool[4]
    for b in pool[:4]:  # make the member bridge the most recently used one
        b.last_cmd_at = 0.0
    pool[4].last_cmd_at = 1e12
    room = CyncGroup(HOME, 0x8013, "Bedroom", [23])
    room.members = [member]
    await room.set_power(1)
    assert pool[4].write.await_count == 1
    assert sum(b.write.await_count for b in pool) == 2


async def test_a_device_with_its_own_session_still_gets_it_directly(monkeypatch):
    pool = setup(monkeypatch, 4)
    dev = device_mod.CyncDevice(15, dev_type=53, name="x", home_id=HOME, home_name="H", entities={})
    dev.tcp_session = pool[2]
    pool[2].last_cmd_at = 1e12
    await dev.set_power(1)
    assert pool[2].write.await_count == 1
