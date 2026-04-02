import unittest
from unittest.mock import patch

from pyhkc import HKCAlarm


def fake_initialize(self):
  self.device_id = "device-id"
  self.securecomm_address = "securecomm-address"


class HKCAlarmTests(unittest.TestCase):
  def test_single_user_status_uses_default_user_code(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch.object(alarm, "_get_status", return_value={"userOptions": {"unset": True}}) as mock_get_status:
      status = alarm.get_system_status()

    self.assertEqual(status["userOptions"]["unset"], True)
    self.assertEqual(mock_get_status.call_args.args[0]["userCode"], "1111")
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

    with patch.object(alarm, "_get_status", side_effect=status_for_user):
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


if __name__ == "__main__":
  unittest.main()
