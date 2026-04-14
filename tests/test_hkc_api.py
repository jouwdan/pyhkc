import unittest
from unittest.mock import Mock, patch

from pyhkc import APP_V3_ROUTE_INVENTORY, DISCOVERED_HOSTS, HKCAlarm


LIVE_STATUS_RESPONSE = {
  "userOptions": {
    "unset": True,
    "partsetA": True,
    "partsetB": True,
    "fullset": True,
    "outputs": False,
    "tempUser": False,
    "virtualRkp": True,
    "viewVideo": True,
    "inputList": True,
  },
  "blocks": [
    {
      "armState": 0,
      "isEnabled": True,
      "inAlarm": False,
      "inFault": False,
      "userAllowed": False,
      "inhibit": False,
    },
    {
      "armState": 0,
      "isEnabled": True,
      "inAlarm": False,
      "inFault": False,
      "userAllowed": True,
      "inhibit": False,
    },
  ],
  "engineerActive": False,
  "alarmEventId": 0,
  "alarmEvents": None,
  "additionalInfo": "Today at 06:48 by U02 Example User",
  "descriptions": {
    "block1": "Main House",
    "block2": "House 2",
    "partseta": "Homeset",
    "partsetb": "Partset B",
  },
}

LIVE_DETAILS_RESPONSE = {
  "type": 6,
  "variant": 4,
  "platform": 24,
  "version": "4.4.0.0",
  "countryCode": 353,
  "serialNumber": 101224369,
  "language": 0,
  "audiolibVersion": "3.0",
  "installationName": "Example Site",
  "siteName": "Example Site",
}

LIVE_INPUTS_RESPONSE = {
  "inputs": [
    {
      "input": 1,
      "inputId": 1,
      "description": "Example Sensor",
      "inputState": 0,
      "inputType": 1,
      "timestamp": "0001-01-01T00:00:00",
      "actionInhibit": True,
      "cameraId": 0,
    },
  ],
  "moreInputs": False,
}

LIVE_REMOTE_KEYPAD_RESPONSE = {
  "greenLed": 0,
  "redLed": 1,
  "amberLed": 1,
  "cursorOn": False,
  "cursorIndex": 0,
  "display": "Example Site",
  "blink": "0000000000000000",
}

def fake_initialize(self):
  self.device_id = "device-id"
  self.securecomm_address = "securecomm-address"


class HKCAlarmTests(unittest.TestCase):
  def test_single_user_status_uses_default_user_code(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch.object(alarm, "post_app_v3", return_value={"userOptions": {"unset": True}}) as mock_post_app_v3:
      status = alarm.get_system_status()

    self.assertEqual(status["userOptions"]["unset"], True)
    self.assertEqual(mock_post_app_v3.call_args.args[0], "status")
    self.assertEqual(mock_post_app_v3.call_args.args[1]["userCode"], "1111")
    self.assertEqual(mock_post_app_v3.call_args.args[1]["includeDescriptions"], True)
    self.assertEqual(alarm.list_user_codes(), [1111])

  def test_multi_user_summary_reports_per_user_block_access(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    def status_for_user(payload):
      user_code = payload["userCode"]
      return {
        "userOptions": {"fullset": user_code == "1111"},
        "descriptions": {"block1": "Main House", "block2": "Guest Suite"},
        "blocks": [
          {"isEnabled": True, "userAllowed": user_code == "1111", "armState": 0},
          {"isEnabled": True, "userAllowed": user_code == "2222", "armState": 0},
        ],
      }

    with patch.object(alarm, "post_app_v3", side_effect=lambda route, payload: status_for_user(payload)):
      summary = alarm.get_user_access_summary()

    self.assertEqual(alarm.list_user_codes(), [1111, 2222])
    self.assertEqual(summary[1111]["allowedBlocks"][0]["description"], "Main House")
    self.assertEqual(summary[1111]["deniedBlocks"][0]["description"], "Guest Suite")
    self.assertEqual(summary[2222]["allowedBlocks"][0]["description"], "Guest Suite")
    self.assertEqual(summary[2222]["userOptions"]["fullset"], False)

  def test_active_user_switch_and_explicit_override_are_supported(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    alarm.set_active_user(2222)

    with patch.object(alarm, "_api_request", return_value={"success": True}) as mock_api_request:
      alarm.arm_fullset()
      alarm.disarm(user_code=1111)

    first_payload = mock_api_request.call_args_list[0].args[2]
    second_payload = mock_api_request.call_args_list[1].args[2]

    self.assertEqual(first_payload["userCode"], "2222")
    self.assertEqual(second_payload["userCode"], "1111")

  def test_read_only_device_helpers_use_v3_device_auth_payload(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    with patch.object(alarm, "_api_request", side_effect=[{"variant": "SW-10270"}, [], {"subscriptionDaysLeft": 0}]) as mock_api_request:
      details = alarm.get_device_details()
      outputs = alarm.get_outputs(user_code=2222)
      temporary_user = alarm.get_temporary_user()

    self.assertEqual(details["variant"], "SW-10270")
    self.assertEqual(outputs, [])
    self.assertEqual(temporary_user["subscriptionDaysLeft"], 0)

    details_call = mock_api_request.call_args_list[0].args
    outputs_call = mock_api_request.call_args_list[1].args
    temporary_user_call = mock_api_request.call_args_list[2].args

    self.assertEqual(details_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/Details")
    self.assertEqual(details_call[2]["hardwareId"], alarm.hardware_id)
    self.assertEqual(details_call[2]["deviceId"], "device-id")
    self.assertEqual(details_call[2]["devicePassword"], "panel-password")
    self.assertEqual(details_call[2]["userCode"], "1111")

    self.assertEqual(outputs_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/Outputs")
    self.assertEqual(outputs_call[2]["userCode"], "2222")

    self.assertEqual(temporary_user_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/GetTemporaryUser")
    self.assertEqual(temporary_user_call[2]["userCode"], "1111")

  def test_live_observed_status_and_device_shapes_are_supported(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch.object(
      alarm,
      "_api_request",
      side_effect=[
        LIVE_STATUS_RESPONSE,
        LIVE_DETAILS_RESPONSE,
        [],
        {"subscriptionDaysLeft": 0},
        LIVE_INPUTS_RESPONSE,
        LIVE_REMOTE_KEYPAD_RESPONSE,
      ],
    ):
      status = alarm.get_system_status()
      details = alarm.get_device_details()
      outputs = alarm.get_outputs()
      temporary_user = alarm.get_temporary_user()
      inputs = alarm.get_all_inputs()
      keypad = alarm.get_remote_keypad()

    self.assertEqual(sorted(status.keys()), sorted(LIVE_STATUS_RESPONSE.keys()))
    self.assertEqual(sorted(status["blocks"][0].keys()), ["armState", "inAlarm", "inFault", "inhibit", "isEnabled", "userAllowed"])
    self.assertEqual(sorted(details.keys()), sorted(LIVE_DETAILS_RESPONSE.keys()))
    self.assertEqual(outputs, [])
    self.assertEqual(temporary_user["subscriptionDaysLeft"], 0)
    self.assertEqual(sorted(inputs[0].keys()), sorted(LIVE_INPUTS_RESPONSE["inputs"][0].keys()))
    self.assertEqual(sorted(keypad.keys()), sorted(LIVE_REMOTE_KEYPAD_RESPONSE.keys()))

  def test_route_inventory_and_hosts_are_exposed(self):
    self.assertIn("AppV3/Device/Status", APP_V3_ROUTE_INVENTORY["device"])
    self.assertIn("hkc.api.securecomm.cloud", DISCOVERED_HOSTS)
    self.assertIn("AppV3/Video/CCTV", HKCAlarm.discovered_routes()["video"])
    self.assertIn("doorbell.securecomm.cloud", HKCAlarm.discovered_hosts())

  def test_public_payload_builders_and_generic_route_post(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    installation_payload = alarm.build_installation_payload(extraFlag=True)
    device_payload = alarm.build_device_payload(user_code=2222, firstInput=5)

    self.assertEqual(installation_payload["installationId"], 123456)
    self.assertEqual(installation_payload["userCode"], "1111")
    self.assertEqual(installation_payload["extraFlag"], True)

    self.assertEqual(device_payload["deviceId"], "device-id")
    self.assertEqual(device_payload["userCode"], "2222")
    self.assertEqual(device_payload["firstInput"], 5)

    with patch.object(alarm, "_api_request", return_value={"ok": True}) as mock_api_request:
      alarm.post_app_v3("status", alarm.build_device_payload())
      alarm.post_app_v3("AppV3/Device/Details", alarm.build_device_payload())

    self.assertEqual(
      mock_api_request.call_args_list[0].args[1],
      "https://hkc.api.securecomm.cloud/AppV3/Device/Status",
    )
    self.assertEqual(
      mock_api_request.call_args_list[1].args[1],
      "https://hkc.api.securecomm.cloud/AppV3/Device/Details",
    )

  def test_request_headers_follow_base_url_and_timeout(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      session = Mock()
      response = Mock()
      response.json.return_value = {"ok": True}
      response.raise_for_status.return_value = None
      session.request.return_value = response
      alarm = HKCAlarm(
        123456,
        "panel-password",
        1111,
        base_url="https://custom.securecomm.example",
        session=session,
        request_timeout=22,
      )

    result = alarm.post_app_v3("status", alarm.build_device_payload())

    self.assertEqual(result["ok"], True)
    self.assertEqual(session.request.call_args.kwargs["headers"]["Host"], "custom.securecomm.example")
    self.assertEqual(session.request.call_args.kwargs["timeout"], 22)

  def test_deprecated_aliases_still_work(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch.object(alarm, "post_app_v3", return_value={"display": "Ready"}) as mock_post_app_v3:
      panel = alarm.get_panel()

    self.assertEqual(panel["display"], "Ready")
    self.assertEqual(mock_post_app_v3.call_args.args[0], "remote_keypad")
    self.assertEqual(mock_post_app_v3.call_args.args[1]["keys"], "")

  def test_get_latest_event_id_uses_live_log_window_behavior(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    def get_logs(event_id, user_code=None):
      if event_id > 126:
        return []
      newest_event_id = min(126, event_id + alarm.LOG_WINDOW_SIZE - 1)
      return [{"eventId": candidate} for candidate in range(newest_event_id, event_id - 1, -1)]

    with patch.object(alarm, "_get_logs", side_effect=get_logs):
      latest_event_id = alarm._get_latest_event_id()

    self.assertEqual(latest_event_id, 126)

  def test_fetch_logs_pages_descending_live_log_windows(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    requested_event_ids = []

    def get_logs(event_id, user_code=None):
      requested_event_ids.append(event_id)
      if event_id > 126:
        return []
      newest_event_id = min(126, event_id + alarm.LOG_WINDOW_SIZE - 1)
      return [{"eventId": candidate} for candidate in range(newest_event_id, event_id - 1, -1)]

    with patch.object(alarm, "_get_latest_event_id", return_value=126), patch.object(alarm, "_get_logs", side_effect=get_logs):
      logs = alarm.fetch_logs(num_previous_logs=35)

    self.assertEqual(requested_event_ids, [100, 73])
    self.assertEqual([log["eventId"] for log in logs[:5]], [126, 125, 124, 123, 122])
    self.assertEqual(logs[-1]["eventId"], 92)
    self.assertEqual(len(logs), 35)

  def test_home_assistant_entity_map_assigns_unique_and_shared_inputs(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    statuses = {
      1111: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": True, "armState": 0},
          {"isEnabled": True, "userAllowed": False, "armState": 0},
        ],
      },
      2222: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": False, "armState": 0},
          {"isEnabled": True, "userAllowed": True, "armState": 0},
        ],
      },
    }
    inputs = {
      1111: [
        {"input": 1, "inputId": 1, "description": "Main Sensor"},
        {"input": 3, "inputId": 3, "description": "Shared Sensor"},
      ],
      2222: [
        {"input": 2, "inputId": 2, "description": "House 2 Sensor"},
        {"input": 3, "inputId": 3, "description": "Shared Sensor"},
      ],
    }

    with patch.object(alarm, "get_users_status", return_value=statuses), patch.object(alarm, "get_users_inputs", return_value=inputs):
      entity_map = alarm.get_home_assistant_entity_map()

    blocks = {block["block"]: block for block in entity_map["blocks"]}
    self.assertEqual(blocks[1]["accessUserCodes"], [1111])
    self.assertEqual(blocks[2]["accessUserCodes"], [2222])
    self.assertEqual([item["inputId"] for item in blocks[1]["inputs"]], [1])
    self.assertEqual([item["inputId"] for item in blocks[2]["inputs"]], [2])
    self.assertEqual([item["inputId"] for item in entity_map["sharedInputs"]], [3])
    self.assertEqual(entity_map["ambiguousInputs"], [])

  def test_home_assistant_entity_map_marks_inputs_ambiguous_for_multi_block_user(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    statuses = {
      1111: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": True, "armState": 0},
          {"isEnabled": True, "userAllowed": True, "armState": 0},
        ],
      },
    }
    inputs = {
      1111: [
        {"input": 7, "inputId": 7, "description": "Shared By Signature"},
      ],
    }

    with patch.object(alarm, "get_users_status", return_value=statuses), patch.object(alarm, "get_users_inputs", return_value=inputs):
      entity_map = alarm.get_home_assistant_entity_map()

    self.assertEqual(entity_map["sharedInputs"], [])
    self.assertEqual(entity_map["blocks"][0]["inputs"], [])
    self.assertEqual(entity_map["blocks"][1]["inputs"], [])
    self.assertEqual(entity_map["ambiguousInputs"][0]["candidateBlocks"], [1, 2])
    self.assertEqual(entity_map["ambiguousInputs"][0]["inputId"], 7)


if __name__ == "__main__":
  unittest.main()
