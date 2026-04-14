# HKC Alarm API Python Wrapper

Python module for interacting with HKC's Alarm API, allowing for easy interactions with the alarm system.

**Note**: This uses a private API, which means it is subject to change without notice and can break at any time. Always be cautious and respectful when using private APIs.

The client is now AppV3-first and several core routes have been validated against the live HKC cloud, but some routes are still only confirmed from the Android app bundle and may need extra app or session context.

To reduce the chance of being rate-limited or blocked, prefer conservative polling:

- `Status`: every 20-30 seconds
- `Inputs`: every 60-90 seconds
- `Outputs`: every 60-90 seconds
- `Logs`: every 120-300 seconds

Avoid overlapping requests, and prefer immediate refreshes after actions over tight polling loops.

## Features

- Retrieve system status.
- Fetch all inputs.
- Inspect read-only panel details, outputs, and temporary-user status.
- View recent logs.
- Arm and disarm the alarm in various modes.
- Configure multiple user codes for the same panel and inspect per-user access.
- Reuse a route inventory extracted from the official HKC SecureComm 2 Android app.
- Reuse generic AppV3 helpers for experimenting with confirmed routes.

## Installation

1. Clone this repository:
```
git clone https://github.com/jasonmadigan/pyhkc
```

2. Navigate to the repository's directory:
```
cd pyhkc
```

3. Install the required packages:
```
pip install -r requirements.txt
```

## Dependencies

- `requests==2.31.0`
- `tenacity==8.3.0`

## Example Usage

```python
from pyhkc import HKCAlarm

# Initialize the system with your credentials.
panel_id = [your-panel-id]  # replace with your panel ID
panel_password = "[your-panel-password]"  # replace with your panel password
user_code = [your-user-code]  # replace with your user code

alarm_system = HKCAlarm(panel_id, panel_password, user_code)

# Retrieve system status.
status = alarm_system.get_system_status()
print("System Status:", status)

# Fetch all inputs.
inputs = alarm_system.get_all_inputs()
print("All Inputs:", inputs)

# View recent logs.
logs = alarm_system.fetch_logs()
print("Recent Logs:", logs)

# Read the current virtual keypad payload.
keypad = alarm_system.get_remote_keypad()
print("Keypad:", keypad)

# Arm the system.
# alarm_system.arm_fullset()

# Disarm the system.
# alarm_system.disarm()
```

Single-user initialization remains unchanged. If you have multiple panel users with different permissions, add their codes with `user_codes` and query their effective access separately:

```python
from pyhkc import HKCAlarm

alarm_system = HKCAlarm(
    panel_id,
    panel_password,
    1111,  # default / active user code
    user_codes=[2222],
)

# Use the original methods with the active user code.
status = alarm_system.get_system_status()

# Or inspect every configured user and their access levels.
access_summary = alarm_system.get_user_access_summary()
print(access_summary[1111]["allowedBlocks"])
print(access_summary[2222]["allowedBlocks"])

# Read-only v3 helpers confirmed against the current app/API.
details = alarm_system.get_device_details()
outputs = alarm_system.get_outputs()
temporary_user = alarm_system.get_temporary_user()
keypad = alarm_system.get_remote_keypad()

# Build a Home Assistant-oriented block/entity mapping.
entity_map = alarm_system.get_home_assistant_entity_map()
for block in entity_map["blocks"]:
    print(block["description"], block["accessUserCodes"], len(block["inputs"]))

# Temporarily act as another configured user.
alarm_system.set_active_user(2222)
guest_status = alarm_system.get_system_status()

# You can also override the user per call without switching the active user.
admin_status = alarm_system.get_system_status(user_code=1111)
```

`get_home_assistant_entity_map()` is conservative:

- it assigns an input to a block only when the set of users who can see that input matches exactly one block's `accessUserCodes`
- it leaves inputs in `sharedInputs` when every configured user can see them
- it leaves inputs in `ambiguousInputs` when the upstream API does not provide enough information to place them safely on one block

The additional read-only helpers are intended for diagnostics and integrations:

- `get_device_details()` returns panel metadata such as variant, platform, installation name, and site name when the upstream API exposes them
- `get_outputs()` returns the current device outputs payload, which may be empty on some panels
- `get_temporary_user()` returns the current temporary-user status for the authenticated panel user
- `get_remote_keypad()` returns the current remote-keypad payload; `get_panel()` remains as a deprecated alias
- `fetch_logs()` uses the confirmed `AppV3/Device/Logs` flow internally and pages descending log windows automatically

## Extracted app routes

The repository includes a route inventory recovered from the official Android
app bundle in `HKC SecureComm2_1.0.11.xapk`
and documented in [docs/extracted_app_routes.md](docs/extracted_app_routes.md).

You can inspect or reuse the recovered routes directly from Python:

```python
from pyhkc import HKCAlarm, APP_V3_ROUTE_INVENTORY, DISCOVERED_HOSTS

alarm = HKCAlarm(panel_id, panel_password, user_code)

print(APP_V3_ROUTE_INVENTORY["device"])
print(DISCOVERED_HOSTS)

status = alarm.post_app_v3("status", alarm.build_device_payload())
details = alarm.post_app_v3("details", alarm.build_device_payload())
```

This gives you a clean way to experiment with routes discovered in the app even
before a dedicated high-level helper exists in `HKCAlarm`.

The client also accepts:

- `session=` to supply your own `requests.Session`
- `request_timeout=` to bound request duration cleanly in long-running integrations such as Home Assistant

## Live-verified AppV3 behavior

The following routes have been exercised successfully against the live HKC cloud:

- `AppV3/App/GetDeviceId`
- `AppV3/Device/Status`
- `AppV3/Device/Details`
- `AppV3/Device/Inputs`
- `AppV3/Device/Outputs`
- `AppV3/Device/GetTemporaryUser`
- `AppV3/Device/RemoteKeypad`
- `AppV3/Device/Logs` with `eventId`

Observed behavior:

- `GetDeviceId` accepts `installationId` as an integer
- `GetDeviceId` accepts `userCode` as a string
- `Outputs` can validly return an empty list
- `GetTemporaryUser` can validly return only `subscriptionDaysLeft`
- `Logs` returns `400` without `eventId`, so `fetch_logs()` seeds and pages log windows internally

Some discovered routes are still only partially understood. In particular, `AppV3/App/GetFeatureSet` returned `400` with the basic installation-auth payload and likely requires additional app or session context.

## Publishing

```bash
python3 setup.py sdist bdist_wheel
twine upload dist/*
```
