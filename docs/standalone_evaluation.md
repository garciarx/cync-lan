# Evaluation: can cync-lan run with no Cync app and no Cync account at all? (2026-11-05)

Goal: run everything from cync-lan and Home Assistant. That means adding new devices, rooms, groups and control, with
nobody signing in to the Cync app, ever, including the day a device comes out of the box.

Tags as in [protocol.md](protocol.md): **confirmed** (seen on our hardware or in a capture), **inferred**,
**unknown**. "Proxy-alt" means [Proxy-alt/cync-lan](https://github.com/Proxy-alt/cync-lan) (MIT), branch
`feature/ha-custom-component`. That fork did a deep static study of the decompiled Android app
(`docs/cloud_independence_research.md`, `docs/ble_provisioning_protocol.md`). Its claims are static analysis
unless it says otherwise. We have not verified them.

## Verdict

**Feasible.** Most of it already works today. One piece is missing: **adding a brand-new device** (Bluetooth
provisioning). There is one hardware unknown that decides how hard it is: whether a Wi-Fi device, once set up, needs
Cync's cloud to "activate" it before it connects. That can be answered with one cheap test (phase 0 below) before
any real building starts.

## What the cloud and the app do today, and who can replace it

| Job | Today | Standalone status |
|---|---|---|
| Day-to-day control (on/off, dim, colour, effects) | cync-lan, local | **done** (confirmed) |
| Device "login" (0x23 hello + auth code) | cync-lan accepts it and does not validate the code | **done** (confirmed: we never check it) |
| TLS to the devices | cync-lan's self-signed cert (devices accept any cert) | **done** (confirmed) |
| Rooms and groups (mesh group membership on the switches) | cync-lan local groups and the Devices & Groups page | **done** (confirmed 2026-11-04) |
| Device list: ids, names, types, mesh keys, rooms | one-time export from the Cync account into `cync_mesh.yaml` | **mostly done**: the yaml is already the source of truth and the page edits it; needs "add device" without an export |
| User sign-in / permissions | Cync account | **not needed**: Home Assistant does it (the page runs behind HA ingress) |
| Phone app | Cync app | HA app and dashboards (already in use: casita-2) |
| **Adding a new device** (Bluetooth pairing, mesh keys, Wi-Fi password) | Cync app over Bluetooth, then one upload of the result to the cloud | **missing**, see below |
| Removing / re-adding a device | Cync app | missing (remove = Bluetooth "delete pairing" or the power-cycle factory reset) |
| Firmware updates | Cync cloud | **given up** (upstream already advises not to upgrade; OTA would need the cloud) |
| Schedules, scenes, away mode | Cync app / cloud | HA automations and scenes |
| Alexa / Google through Cync | Cync cloud | HA's own Alexa / Google integrations |

## Adding a new device: what is known

How the official app does it (Proxy-alt, static analysis of the app, **inferred**):
1. The app finds the device over Bluetooth. Factory-new devices advertise the name `telink_mesh1`, with
   Telink's company id `0x0211` (our own control packets carry the same `11 02`, which is **confirmed**).
2. It pairs with the factory mesh credentials, then gives the device the home's mesh name, password and key. This is
   the standard Telink mesh pairing, also implemented by `google/python-dimond` (open source, works on real Telink
   devices).
3. It gives the device its mesh address, groups and the time.
4. For Wi-Fi devices only, it sends the Wi-Fi name and password as encrypted mesh commands (`F6 11 02 02`, in
   chunks).
5. **It uploads the result to the cloud** (`PUT .../property`, the whole home). By the app's own step order, this
   is 1 of about 20 steps, and it happens after the device is already set up.

What that means for us:
- Device identity (id, mesh address) is decided **on the phone**, not issued by the cloud (**inferred**). So
  cync-lan can decide it: we already hand out ids (local groups count down from `0x80FE`).
- Adding a device to an **existing home** needs that home's mesh name/password. We have it per home from the export
  (`access_key` and the home id). The app can also read it off any paired device over Bluetooth (**inferred**).
- A **brand-new home** with no account: the mesh name/password can simply be made up (**inferred**: the app derives
  them from the home's own name and id).

Prior art: Proxy-alt ships an experimental `cync-lan-ble-provision` command-line tool for steps 1-2. Its own notes
say it is **untested on real hardware** and does not yet do the Wi-Fi step.

## The deciding unknown

**What does a freshly set-up Wi-Fi device do first?** Wi-Fi devices come from the XLink platform.
- Possibility A: it connects straight to `cm.gelighting.com:23779`. That is cync-lan through our DNS redirect,
  and we accept any auth code. Then the whole onboarding is local.
- Possibility B: it first calls a cloud HTTP service to "activate" and get its auth code or `switchID` (the 0x23
  queue id). Then it may never connect anywhere until that succeeds.

The answer is **unknown**. Signs pointing to A: the 0x23 auth code is never validated by us and the devices still
work, and the app's own Wi-Fi step carries only the Wi-Fi name, password and device type. Sign pointing to B: the
app saves per-device `subKey`/`accessKey` values *that the device reports back* at the end of the Wi-Fi step
(Proxy-alt, finding 9), so the device has some XLink identity of its own.

A side effect for multi-home: today a connecting device's home is found from its 0x23 queue id = cloud `switchID`
(**confirmed**). A device the cloud never saw has a queue id we have no record of. That is fine with one home or a
`bridges:` list, but we would need a new rule (for example: remember the queue id at onboarding).

## Where the Bluetooth radio lives (practical, important)

You pair a device standing next to it, and wall switches are in the walls. Options:
1. **Web Bluetooth from the phone, inside the add-on's own page** (Devices & Groups tab). The phone is the radio,
   and nothing new needs to be installed. It works in Chrome on Android over HTTPS (Nabu Casa or HA with TLS).
   **Not on iPhone Safari** (Apple has no Web Bluetooth; the Bluefy browser does). Telink's AES-ECB can be done in the
   browser.
2. A Bluetooth adapter on the HA box (add-on with host D-Bus access). Simple, but only reaches devices near the box.
3. Becoming an HA integration that uses HA's own Bluetooth, including ESPHome Bluetooth proxies placed around the
   house. This is the route Proxy-alt took. It is a big restructure of this project (add-on to integration).

Recommendation: **option 1**, with option 2 as a fallback for Bluetooth-only bulbs you can bring near the box.

## Plan, cheapest and most decisive first

| Phase | What | Answers | Effort |
|---|---|---|---|
| 0 | Re-add one spare Wi-Fi device with the official app while watching (a) your DNS server's query log for every name the device looks up, and (b) the cync-lan app-proxy/MITM logs. | Possibility A or B. If the device only asks for `cm.gelighting.com`, A is very likely | 1 evening, no code |
| 1 | Bluetooth pairing of a **Bluetooth-only bulb into an existing home**: scan, pair, mesh keys, address, add to the yaml, appears in HA. Based on python-dimond's proven crypto plus Proxy-alt's notes. | Telink pairing works for Cync with our keys | 2-3 sessions |
| 2 | Wi-Fi devices: the Wi-Fi password step, then the device connects to cync-lan. If phase 0 said B: try a fake activation answer, or keep "add with the app once" for Wi-Fi devices. | Fully local onboarding | 2-4 sessions if A; open-ended if B |
| 3 | No-account mode: create a home from scratch (made-up mesh keys), remove/factory-reset from the page, and a backup of the yaml (it is now the only copy of the mesh keys). | Never touching the Cync account | 2 sessions |

Go / no-go after phase 0: if B, and a fake activation is not possible, the fallback is still good. In that case the
Cync app is needed **only on the day a Wi-Fi device is added**. Everything after that is local, and Bluetooth-only
devices are still fully local.

## Risks

- A failed pairing leaves the device in a half-paired state. The fix is a factory reset (power-cycle sequence),
  so this is recoverable. Test on a spare device first.
- Losing `cync_mesh.yaml` would mean losing the mesh keys, so every device would need a reset. Backups are
  mandatory in standalone mode (the page already keeps 10 timestamped copies; an off-box copy is still needed).
- No firmware updates, ever (already the case under DNS redirection).
- Cync could change the protocol in new firmware. Devices that never update are not affected.
- This all comes from reverse engineering for interoperability with your own devices. Proxy-alt's research is MIT,
  so we can reuse it with credit.
