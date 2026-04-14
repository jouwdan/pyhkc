import logging
import uuid
import warnings
from typing import Iterable
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .routes import APP_V3_ROUTE_ALIASES, APP_V3_ROUTE_INVENTORY, DISCOVERED_HOSTS


class HKCAlarm:
  LOG_WINDOW_SIZE = 27

  def __init__(
    self,
    panel_id,
    panel_password,
    user_code,
    base_url="https://hkc.api.securecomm.cloud",
    log_level=logging.INFO,
    user_codes=None,
    session=None,
    request_timeout=15,
  ):
    self.base_url = base_url
    self.panel_id = int(panel_id)
    self.panel_password = panel_password
    self.user_codes = self._normalize_user_codes(user_code, user_codes)
    self.user_code = self.user_codes[0]
    self.session = session or requests.Session()
    self.request_timeout = request_timeout
    self.securecomm_address = ""  # legacy compatibility only
    self.hardware_id = str(uuid.uuid4())
    self.device_id = None  # fetched during init
    self.logger = logging.getLogger(__name__)
    self.logger.setLevel(log_level)

    self.logger.info("Initializing HKCAlarm")
    self._initialize()

  @staticmethod
  def _coerce_user_code(user_code):
    return int(user_code)

  @classmethod
  def _normalize_user_codes(cls, primary_user_code, user_codes=None):
    normalized_codes = []

    def add_code(candidate):
      code = cls._coerce_user_code(candidate)
      if code not in normalized_codes:
        normalized_codes.append(code)

    add_code(primary_user_code)

    if user_codes is None:
      return normalized_codes

    if isinstance(user_codes, Iterable) and not isinstance(user_codes, (str, bytes)):
      for candidate in user_codes:
        add_code(candidate)
      return normalized_codes

    add_code(user_codes)
    return normalized_codes

  def _resolve_user_code(self, user_code=None):
    if user_code is None:
      return self.user_code
    return self._coerce_user_code(user_code)

  @classmethod
  def _normalize_requested_user_codes(cls, user_codes):
    if isinstance(user_codes, Iterable) and not isinstance(user_codes, (str, bytes)):
      return list(dict.fromkeys(cls._coerce_user_code(candidate) for candidate in user_codes))
    return [cls._coerce_user_code(user_codes)]

  @staticmethod
  def _block_description(descriptions, block_number):
    return descriptions.get(f"block{block_number}", f"Block {block_number}")

  @staticmethod
  def _input_key(input_data):
    return input_data.get("inputId", input_data.get("input"))

  def _build_block_access_map(self, statuses):
    blocks = {}

    for code, status in statuses.items():
      descriptions = status.get("descriptions", {})
      for block_number, block in enumerate(status.get("blocks", []), start=1):
        if not block.get("isEnabled"):
          continue

        existing = blocks.setdefault(block_number, {
          "block": block_number,
          "description": self._block_description(descriptions, block_number),
          "isEnabled": True,
          "armState": block.get("armState"),
          "accessUserCodes": [],
        })

        if block.get("userAllowed") and code not in existing["accessUserCodes"]:
          existing["accessUserCodes"].append(code)

    return {
      "blocks": [
        {
          **block,
          "accessUserCodes": sorted(block["accessUserCodes"]),
        }
        for _, block in sorted(blocks.items())
      ]
    }

  def _initialize(self):
    # get device id first - required for appv3
    self.device_id = self._get_device_id()
    self.logger.info(f"Obtained device ID: {self.device_id}")
    self.securecomm_address = self.get_system_status().get('secureCommAddress', self.securecomm_address)

  def list_user_codes(self):
    return list(self.user_codes)

  def add_user(self, user_code):
    normalized_code = self._coerce_user_code(user_code)
    if normalized_code not in self.user_codes:
      self.user_codes.append(normalized_code)
    return normalized_code

  def set_active_user(self, user_code):
    normalized_code = self._coerce_user_code(user_code)
    if normalized_code not in self.user_codes:
      raise ValueError(f"User code {normalized_code} is not configured on this client")
    self.user_code = normalized_code
    return self.user_code

  def register_mobile(self, app_version="1.0.2", hardware_id="", description=""):
    warnings.warn(
      "register_mobile() targets a legacy registration flow that is not used by the current official app.",
      DeprecationWarning,
      stacklevel=2,
    )
    data = {
      "appType": 5,
      "appVersion": app_version,
      "deviceId": "0",
      "panelList": [{"panelId": self.panel_id, "description": description, "options": 2}],
      "hardwareId": hardware_id,
      "soundlist": []
    }
    return self._mobile_register(data)

  @classmethod
  def discovered_routes(cls):
    return {
      group: list(routes)
      for group, routes in APP_V3_ROUTE_INVENTORY.items()
    }

  @classmethod
  def discovered_hosts(cls):
    return list(DISCOVERED_HOSTS)

  def build_installation_payload(self, user_code=None, **extra):
    resolved_user_code = self._resolve_user_code(user_code)
    payload = {
      "hardwareId": self.hardware_id,
      "installationId": self.panel_id,
      "devicePassword": self.panel_password,
      "userCode": str(resolved_user_code),
    }
    payload.update(extra)
    return payload

  def build_device_payload(self, user_code=None, **extra):
    payload = self._device_request_payload(user_code=user_code)
    payload.update(extra)
    return payload

  def post_app_v3(self, route, payload):
    normalized_route = APP_V3_ROUTE_ALIASES.get(route, route)
    if not normalized_route.startswith("AppV3/"):
      raise ValueError(f"Unknown AppV3 route or alias: {route}")
    return self._api_request("POST", f"{self.base_url}/{normalized_route}", payload)

  def get_system_status(self, user_code=None):
    response = self.post_app_v3("status", self.build_device_payload(user_code=user_code, includeDescriptions=True))
    self.securecomm_address = response.get("secureCommAddress", self.securecomm_address)
    return response

  def get_users_status(self, user_codes=None):
    target_user_codes = self._normalize_requested_user_codes(user_codes) if user_codes is not None else self.list_user_codes()
    return {code: self.get_system_status(user_code=code) for code in target_user_codes}

  def get_users_inputs(self, user_codes=None):
    target_user_codes = self._normalize_requested_user_codes(user_codes) if user_codes is not None else self.list_user_codes()
    return {code: self.get_all_inputs(user_code=code) for code in target_user_codes}

  def get_block_access_map(self, user_codes=None):
    statuses = self.get_users_status(user_codes=user_codes)
    return self._build_block_access_map(statuses)

  def get_user_access_summary(self, user_codes=None):
    summaries = {}
    for code, status in self.get_users_status(user_codes=user_codes).items():
      descriptions = status.get("descriptions", {})
      allowed_blocks = []
      denied_blocks = []

      for block_number, block in enumerate(status.get("blocks", []), start=1):
        if not block.get("isEnabled"):
          continue

        block_summary = {
          "block": block_number,
          "description": self._block_description(descriptions, block_number),
          "armState": block.get("armState"),
        }

        if block.get("userAllowed"):
          allowed_blocks.append(block_summary)
        else:
          denied_blocks.append(block_summary)

      summaries[code] = {
        "userOptions": status.get("userOptions", {}),
        "allowedBlocks": allowed_blocks,
        "deniedBlocks": denied_blocks,
      }

    return summaries

  def get_home_assistant_entity_map(self, user_codes=None):
    statuses = self.get_users_status(user_codes=user_codes)
    inputs_by_user = self.get_users_inputs(user_codes=statuses.keys())
    block_map = self._build_block_access_map(statuses)
    configured_user_codes = list(statuses.keys())
    configured_user_set = frozenset(configured_user_codes)

    block_visibility_signatures = {}
    for block in block_map["blocks"]:
      signature = frozenset(block["accessUserCodes"])
      block_visibility_signatures.setdefault(signature, []).append(block["block"])

    user_input_index = {}
    merged_inputs = {}
    input_visible_to = {}
    for code, inputs in inputs_by_user.items():
      indexed_inputs = {}
      for input_data in inputs:
        input_key = self._input_key(input_data)
        indexed_inputs[input_key] = input_data
        merged_inputs.setdefault(input_key, input_data)
        input_visible_to.setdefault(input_key, set()).add(code)
      user_input_index[code] = indexed_inputs

    block_inputs = {block["block"]: [] for block in block_map["blocks"]}
    shared_inputs = []
    ambiguous_inputs = []

    for input_key, input_data in sorted(merged_inputs.items(), key=lambda item: item[0]):
      visible_user_codes = sorted(input_visible_to.get(input_key, set()))
      visibility_signature = frozenset(visible_user_codes)
      candidate_blocks = block_visibility_signatures.get(visibility_signature, [])
      annotated_input = dict(input_data)
      annotated_input["visibleUserCodes"] = visible_user_codes

      if len(candidate_blocks) == 1:
        block_inputs[candidate_blocks[0]].append(annotated_input)
      elif len(candidate_blocks) > 1:
        ambiguous_input = dict(annotated_input)
        ambiguous_input["candidateBlocks"] = candidate_blocks
        ambiguous_inputs.append(ambiguous_input)
      elif visibility_signature == configured_user_set:
        shared_inputs.append(annotated_input)
      else:
        ambiguous_input = dict(annotated_input)
        ambiguous_input["candidateBlocks"] = candidate_blocks
        ambiguous_inputs.append(ambiguous_input)

    for block in block_map["blocks"]:
      block["inputs"] = block_inputs[block["block"]]

    return {
      "panel": {
        "panelId": self.panel_id,
        "deviceId": self.device_id,
      },
      "users": {
        code: {
          "allowedBlocks": [
            block["block"]
            for block in block_map["blocks"]
            if code in block["accessUserCodes"]
          ],
          "visibleInputs": sorted(user_input_index[code].keys()),
        }
        for code in configured_user_codes
      },
      "blocks": block_map["blocks"],
      "sharedInputs": shared_inputs,
      "ambiguousInputs": ambiguous_inputs,
    }

  def arm_partset_a(self, user_code=None):
    return self._arm_or_disarm(command=1, block=0, user_code=user_code)

  def arm_partset_b(self, user_code=None):
    return self._arm_or_disarm(command=2, block=0, user_code=user_code)

  def arm_fullset(self, user_code=None):
    return self._arm_or_disarm(command=3, block=0, user_code=user_code)

  def disarm(self, user_code=None):
    return self._arm_or_disarm(command=0, block=0, user_code=user_code)

  def fetch_logs(self, num_previous_logs=10, user_code=None):
    latest_event_id = self._get_latest_event_id(user_code=user_code)
    if latest_event_id is None:
      return []

    oldest_event_id = max(1, latest_event_id - self.LOG_WINDOW_SIZE + 1)
    logs = []
    seen_event_ids = set()

    while len(logs) < num_previous_logs and oldest_event_id >= 1:
      logs_chunk = self._get_logs(oldest_event_id, user_code=user_code)
      if not logs_chunk:
        break

      for log in logs_chunk:
        event_id = log.get("eventId")
        if event_id in seen_event_ids:
          continue
        seen_event_ids.add(event_id)
        logs.append(log)

      if oldest_event_id == 1:
        break

      oldest_event_id = max(1, oldest_event_id - self.LOG_WINDOW_SIZE)

    return logs[:num_previous_logs]

  def get_all_inputs(self, user_code=None):
    all_inputs = []
    more_inputs = True
    first_input = 1

    while more_inputs:
      inputs_response = self._get_inputs(first_input=first_input, user_code=user_code)

      current_inputs = inputs_response.get("inputs", [])
      all_inputs.extend(current_inputs)
      more_inputs = inputs_response.get("moreInputs", False)

      if more_inputs and current_inputs:
        first_input = current_inputs[-1].get("input", 1) + 1

    return all_inputs

  def check_login(self, user_code=None):
    system_status = self.get_system_status(user_code=user_code)
    if "userOptions" in system_status:
      return True
    if "success" in system_status and system_status["success"] is False:
      return False
    raise RuntimeError("Unexpected response format from get_system_status")

  def get_remote_keypad(self, user_code=None):
    return self.post_app_v3("remote_keypad", self.build_device_payload(user_code=user_code, keys=""))

  def get_panel(self):
    warnings.warn(
      "get_panel() is deprecated; use get_remote_keypad() instead.",
      DeprecationWarning,
      stacklevel=2,
    )
    return self.get_remote_keypad()

  def get_device_details(self, user_code=None):
    return self.post_app_v3("details", self.build_device_payload(user_code=user_code))

  def get_outputs(self, user_code=None):
    return self.post_app_v3("outputs", self.build_device_payload(user_code=user_code))

  def get_temporary_user(self, user_code=None):
    return self.post_app_v3("get_temporary_user", self.build_device_payload(user_code=user_code))

  # Private methods for direct API calls

  @retry(wait=wait_exponential(multiplier=1, min=4, max=30), stop=stop_after_attempt(5), reraise=True)
  def _api_request(self, method, url, data=None):
    try:
      self.logger.debug(f"Making {method} request to {url} with data: {data}")
      response = self.session.request(
        method,
        url,
        headers=self._request_headers(),
        json=data,
        timeout=self.request_timeout,
      )
      response.raise_for_status()
      return response.json()
    except requests.exceptions.RequestException as e:
      self.logger.error(f"Request to {url} failed: {str(e)}")
      raise

  def _mobile_register(self, data):
    warnings.warn(
      "_mobile_register() targets a legacy registration flow that is not used by the current official app.",
      DeprecationWarning,
      stacklevel=2,
    )
    return self._api_request("POST", f"{self.base_url}/AppV3/Registration/MobileRegister", data)

  def _get_status(self, data):
    return self.post_app_v3("status", data)

  def _request_headers(self):
    parsed = urlparse(self.base_url)
    host = parsed.netloc or "hkc.api.securecomm.cloud"
    return {
      "Host": host,
      "accept": "application/json, text/plain, */*",
      "content-type": "application/json;charset=utf-8",
      "user-agent": "okhttp/4.9.2",
    }

  def _device_request_payload(self, user_code=None):
    resolved_user_code = self._resolve_user_code(user_code)
    return {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(resolved_user_code),
    }

  def _arm_or_disarm(self, command, block, user_code=None):
    data = self.build_device_payload(user_code=user_code, command=command, block=block, inhibit=False)
    return self.post_app_v3("arming", data)

  def _get_logs(self, event_id, user_code=None):
    request_data = self.build_device_payload(user_code=user_code, eventId=event_id)
    return self.post_app_v3("logs", request_data)

  def _get_inputs(self, first_input=1, user_code=None):
    request_data = self.build_device_payload(user_code=user_code, firstInput=first_input)
    return self.post_app_v3("inputs", request_data)

  def _get_device_id(self, user_code=None):
    data = self.build_installation_payload(user_code=user_code)
    response = self.post_app_v3("get_device_id", data)
    return response.get("deviceId")

  def _get_latest_event_id(self, user_code=None):
    lower_bound = 1
    lower_logs = self._get_logs(lower_bound, user_code=user_code)
    if not lower_logs:
      return None

    upper_bound = lower_bound
    while True:
      candidate = upper_bound * 2
      if not self._get_logs(candidate, user_code=user_code):
        upper_bound = candidate
        break
      lower_bound = candidate
      upper_bound = candidate

    while lower_bound + 1 < upper_bound:
      midpoint = (lower_bound + upper_bound) // 2
      if self._get_logs(midpoint, user_code=user_code):
        lower_bound = midpoint
      else:
        upper_bound = midpoint

    return lower_bound
