"""Route inventory extracted from the official HKC SecureComm 2 Android app.

The current inventory was recovered from the React Native bundle shipped in
`HKC SecureComm2_1.0.11.xapk`.
"""

DISCOVERED_HOSTS = (
  "hkc.api.securecomm.cloud",
  "hkc.securecomm.cloud",
  "doorbell.securecomm.cloud",
  "54.216.251.71:9000",
)

APP_V3_ROUTE_INVENTORY = {
  "app": (
    "AppV3/App/GetDeviceId",
    "AppV3/App/GetFeatureSet",
    "AppV3/App/GetInstallerLogo",
    "AppV3/App/Registering",
  ),
  "device": (
    "AppV3/Device/Arming",
    "AppV3/Device/ControlOutput",
    "AppV3/Device/Details",
    "AppV3/Device/GetTemporaryUser",
    "AppV3/Device/Inhibit",
    "AppV3/Device/Inputs",
    "AppV3/Device/InstallationStatusUpdate",
    "AppV3/Device/Logs",
    "AppV3/Device/Outputs",
    "AppV3/Device/RemoteKeypad",
    "AppV3/Device/SetTemporaryUser",
    "AppV3/Device/Status",
  ),
  "pircam": (
    "AppV3/PirCam/GetLive",
    "AppV3/PirCam/GetVerification",
  ),
  "video": (
    "AppV3/Video/CCTV",
    "AppV3/Video/CCTVPlaybackUrl",
  ),
}

APP_V3_ROUTE_ALIASES = {
  "get_device_id": "AppV3/App/GetDeviceId",
  "get_feature_set": "AppV3/App/GetFeatureSet",
  "get_installer_logo": "AppV3/App/GetInstallerLogo",
  "registering": "AppV3/App/Registering",
  "arming": "AppV3/Device/Arming",
  "control_output": "AppV3/Device/ControlOutput",
  "details": "AppV3/Device/Details",
  "get_temporary_user": "AppV3/Device/GetTemporaryUser",
  "inhibit": "AppV3/Device/Inhibit",
  "inputs": "AppV3/Device/Inputs",
  "installation_status_update": "AppV3/Device/InstallationStatusUpdate",
  "logs": "AppV3/Device/Logs",
  "outputs": "AppV3/Device/Outputs",
  "remote_keypad": "AppV3/Device/RemoteKeypad",
  "set_temporary_user": "AppV3/Device/SetTemporaryUser",
  "status": "AppV3/Device/Status",
  "pircam_live": "AppV3/PirCam/GetLive",
  "pircam_verification": "AppV3/PirCam/GetVerification",
  "cctv": "AppV3/Video/CCTV",
  "cctv_playback_url": "AppV3/Video/CCTVPlaybackUrl",
}

APP_V3_PAYLOAD_HINTS = {
  "AppV3/App/GetDeviceId": "installation_auth",
  "AppV3/App/GetFeatureSet": "installation_auth_or_app_config",
  "AppV3/App/GetInstallerLogo": "installer_or_site_context",
  "AppV3/App/Registering": "doorbell_or_mobile_registration",
  "AppV3/Device/Arming": "device_auth_plus_command_fields",
  "AppV3/Device/ControlOutput": "device_auth_plus_output_fields",
  "AppV3/Device/Details": "device_auth",
  "AppV3/Device/GetTemporaryUser": "device_auth",
  "AppV3/Device/Inhibit": "device_auth_plus_input_fields",
  "AppV3/Device/Inputs": "device_auth_plus_pagination",
  "AppV3/Device/InstallationStatusUpdate": "device_auth_or_installation_context",
  "AppV3/Device/Logs": "device_auth_plus_event_window",
  "AppV3/Device/Outputs": "device_auth",
  "AppV3/Device/RemoteKeypad": "device_auth_plus_keys",
  "AppV3/Device/SetTemporaryUser": "device_auth_plus_temporary_user_fields",
  "AppV3/Device/Status": "device_auth",
  "AppV3/PirCam/GetLive": "camera_context",
  "AppV3/PirCam/GetVerification": "camera_context",
  "AppV3/Video/CCTV": "camera_context",
  "AppV3/Video/CCTVPlaybackUrl": "camera_context_plus_time_window",
}


def all_discovered_routes():
  return [
    route
    for group in APP_V3_ROUTE_INVENTORY.values()
    for route in group
  ]
