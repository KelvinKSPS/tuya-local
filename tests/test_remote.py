"""Tests for the remote entity."""

import asyncio
import json
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_local.const import (
    CONF_DEVICE_ID,
    CONF_PROTOCOL_VERSION,
    CONF_TYPE,
    DOMAIN,
)
from custom_components.tuya_local.remote import (
    CMD_SEND,
    CMD_SEND_RF,
    TuyaLocalRemote,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_init_entry(hass):
    """Test the initialisation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TYPE: "ir_remote_sensors",
            CONF_DEVICE_ID: "dummy",
            CONF_PROTOCOL_VERSION: "auto",
        },
    )
    # although async, the async_add_entities function passed to
    # async_setup_entry is called truly asynchronously. If we use
    # AsyncMock, it expects us to await the result.
    m_add_entities = Mock()
    m_device = AsyncMock()

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["dummy"] = {}
    hass.data[DOMAIN]["dummy"]["device"] = m_device

    await async_setup_entry(hass, entry, m_add_entities)
    assert type(hass.data[DOMAIN]["dummy"]["remote"]) is TuyaLocalRemote
    m_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_init_entry_fails_if_device_has_no_remote(hass):
    """Test initialisation when device has no matching entity"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TYPE: "smartplugv1",
            CONF_DEVICE_ID: "dummy",
            CONF_PROTOCOL_VERSION: "auto",
        },
    )
    # although async, the async_add_entities function passed to
    # async_setup_entry is called truly asynchronously. If we use
    # AsyncMock, it expects us to await the result.
    m_add_entities = Mock()
    m_device = AsyncMock()

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["dummy"] = {}
    hass.data[DOMAIN]["dummy"]["device"] = m_device
    try:
        await async_setup_entry(hass, entry, m_add_entities)
        assert False
    except ValueError:
        pass
    m_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_init_entry_fails_if_config_is_missing(hass):
    """Test initialisation when device has no matching entity"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TYPE: "non_existing",
            CONF_DEVICE_ID: "dummy",
            CONF_PROTOCOL_VERSION: "auto",
        },
    )
    # although async, the async_add_entities function passed to
    # async_setup_entry is called truly asynchronously. If we use
    # AsyncMock, it expects us to await the result.
    m_add_entities = Mock()
    m_device = AsyncMock()

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["dummy"] = {}
    hass.data[DOMAIN]["dummy"]["device"] = m_device
    try:
        await async_setup_entry(hass, entry, m_add_entities)
        assert False
    except ValueError:
        pass
    m_add_entities.assert_not_called()


def _make_remote(has_receive=True, has_control=False, has_delay=False, has_type=False):
    """Create a TuyaLocalRemote with mocked internals."""
    device = MagicMock()
    device._hass = MagicMock()
    device._name = "Test Hub"
    device.unique_id = "test_remote_123"
    device.dev_cid = None  # standalone device — not a gateway sub-device
    device.dev_id = "hub_device_id"
    device.async_set_properties = AsyncMock()
    device.async_refresh = AsyncMock()
    device.anticipate_property_value = MagicMock()

    remote = object.__new__(TuyaLocalRemote)
    remote._device = device
    remote._config = MagicMock()
    remote._config.name = "Test Remote"
    remote._config.translation_key = None
    remote._config.translation_only_key = None
    remote._config.translation_placeholders = None
    remote._config.entity_category = None
    remote._config.config_id = "test_remote"
    remote._attr_dps = []
    remote._attr_translation_key = None
    remote._attr_translation_placeholders = None
    remote._attr_is_on = True
    remote._attr_supported_features = 0

    remote._send_dp = MagicMock()
    remote._send_dp.id = 201
    remote._send_dp.get_values_to_set.side_effect = lambda dev, val, d: {201: val}
    remote._send_dp.async_set_value = AsyncMock()

    if has_receive:
        remote._receive_dp = MagicMock()
        remote._receive_dp.id = 202
    else:
        remote._receive_dp = None

    if has_control:
        remote._control_dp = MagicMock()
        remote._control_dp.get_values_to_set.side_effect = lambda dev, val, d: {
            "control": val
        }
        remote._control_dp.async_set_value = AsyncMock()
    else:
        remote._control_dp = None

    if has_delay:
        remote._delay_dp = MagicMock()
        remote._delay_dp.get_values_to_set.side_effect = lambda dev, val, d: {
            "delay": val
        }
    else:
        remote._delay_dp = None

    if has_type:
        remote._type_dp = MagicMock()
        remote._type_dp.get_values_to_set.side_effect = lambda dev, val, d: {
            "type": val
        }
    else:
        remote._type_dp = None

    remote._code_storage = MagicMock()
    remote._code_storage.async_load = AsyncMock(return_value={})
    remote._code_storage.async_save = AsyncMock()
    remote._code_storage.async_delay_save = MagicMock()
    remote._flag_storage = MagicMock()
    remote._flag_storage.async_load = AsyncMock(return_value={})
    remote._flag_storage.async_delay_save = MagicMock()
    remote._storage_loaded = False
    remote._codes = {}
    remote._flags = defaultdict(int)
    remote._lock = asyncio.Lock()

    return remote


class TestExtractCodes:
    def test_b64_prefix(self):
        remote = _make_remote()
        remote._storage_loaded = True
        result = remote._extract_codes(["b64:AAAA"])
        assert result == [["AAAA"]]

    def test_rf_prefix(self):
        remote = _make_remote()
        remote._storage_loaded = True
        result = remote._extract_codes(["rf:BBBB"])
        assert result == [["rf:BBBB"]]

    def test_storage_lookup(self):
        remote = _make_remote()
        remote._storage_loaded = True
        remote._codes = {"tv": {"power": "CODE123"}}
        result = remote._extract_codes(["power"], subdevice="tv")
        assert result == [["CODE123"]]

    def test_storage_lookup_list(self):
        remote = _make_remote()
        remote._storage_loaded = True
        remote._codes = {"tv": {"power": ["CODE_ON", "CODE_OFF"]}}
        result = remote._extract_codes(["power"], subdevice="tv")
        assert result == [["CODE_ON", "CODE_OFF"]]

    def test_missing_subdevice_raises(self):
        remote = _make_remote()
        remote._storage_loaded = True
        with pytest.raises(ValueError, match="device must be specified"):
            remote._extract_codes(["power"])

    def test_missing_command_raises(self):
        remote = _make_remote()
        remote._storage_loaded = True
        remote._codes = {"tv": {}}
        with pytest.raises(ValueError, match="not found"):
            remote._extract_codes(["volume_up"], subdevice="tv")

    def test_multiple_commands(self):
        remote = _make_remote()
        remote._storage_loaded = True
        result = remote._extract_codes(["b64:AAA", "b64:BBB"])
        assert len(result) == 2


class TestEncodeSendCode:
    def test_ir_default(self):
        remote = _make_remote()
        dps = remote._encode_send_code("TESTCODE", 300)
        assert 201 in dps
        payload = json.loads(dps[201])
        assert payload["control"] == CMD_SEND
        assert "TESTCODE" in payload["key1"]
        assert payload["delay"] == 300

    def test_rf_mode(self):
        remote = _make_remote()
        dps = remote._encode_send_code("RFCODE", 0, is_rf=True)
        assert 201 in dps
        payload = json.loads(dps[201])
        assert payload["control"] == CMD_SEND_RF
        assert payload["key1"]["code"] == "RFCODE"

    def test_with_control_dp(self):
        remote = _make_remote(has_control=True)
        dps = remote._encode_send_code("CODE", 100)
        assert "control" in dps
        assert dps["control"] == CMD_SEND
        assert 201 in dps
        assert dps[201] == "CODE"

    def test_with_control_and_delay(self):
        remote = _make_remote(has_control=True, has_delay=True)
        dps = remote._encode_send_code("CODE", 500)
        assert "delay" in dps
        assert dps["delay"] == 500

    def test_with_control_and_type(self):
        remote = _make_remote(has_control=True, has_type=True)
        dps = remote._encode_send_code("CODE", 100)
        assert "type" in dps
        assert dps["type"] == 0


class TestAsyncSendCommand:
    @pytest.mark.asyncio
    async def test_send_b64_command(self):
        remote = _make_remote()
        await remote.async_send_command(["b64:TESTCODE"], num_repeats=1)
        remote._device.async_set_properties.assert_awaited_once()
        assert remote._storage_loaded is True

    @pytest.mark.asyncio
    async def test_send_rf_command(self):
        remote = _make_remote()
        await remote.async_send_command(["rf:RFCODE"], num_repeats=1)
        call_args = remote._device.async_set_properties.call_args[0][0]
        payload = json.loads(call_args[201])
        assert payload["control"] == CMD_SEND_RF

    @pytest.mark.asyncio
    async def test_send_stored_command(self):
        remote = _make_remote()
        remote._codes = {"tv": {"power": "STORED_CODE"}}
        await remote.async_send_command(["power"], device="tv", num_repeats=1)
        remote._device.async_set_properties.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_toggle_command(self):
        remote = _make_remote()
        remote._codes = {"tv": {"power": ["ON_CODE", "OFF_CODE"]}}
        await remote.async_send_command(["power"], device="tv", num_repeats=1)
        # First call uses flag=0 (ON_CODE)
        remote._device.async_set_properties.assert_awaited_once()
        # Flag should have been toggled
        assert remote._flags["tv"] == 1
        remote._flag_storage.async_delay_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_invalid_command_raises(self):
        remote = _make_remote()
        remote._codes = {"tv": {}}
        with pytest.raises(ValueError):
            await remote.async_send_command(["missing"], device="tv", num_repeats=1)

    @pytest.mark.asyncio
    async def test_loads_storage_on_first_send(self):
        remote = _make_remote()
        assert remote._storage_loaded is False
        await remote.async_send_command(["b64:CODE"], num_repeats=1)
        assert remote._storage_loaded is True
        remote._code_storage.async_load.assert_awaited_once()


class TestAsyncDeleteCommand:
    @pytest.mark.asyncio
    async def test_delete_command(self):
        remote = _make_remote()
        remote._codes = {"tv": {"power": "CODE", "volume": "CODE2"}}
        remote._storage_loaded = True
        await remote.async_delete_command(command=["power"], device="tv")
        assert "power" not in remote._codes["tv"]
        assert "volume" in remote._codes["tv"]

    @pytest.mark.asyncio
    async def test_delete_last_command_cleans_up(self):
        remote = _make_remote()
        remote._codes = {"tv": {"power": "CODE"}}
        remote._flags["tv"] = 1
        remote._storage_loaded = True
        await remote.async_delete_command(command=["power"], device="tv")
        assert "tv" not in remote._codes
        remote._flag_storage.async_delay_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_missing_device_raises(self):
        remote = _make_remote()
        remote._storage_loaded = True
        with pytest.raises(ValueError, match="Device not found"):
            await remote.async_delete_command(command=["power"], device="unknown")

    @pytest.mark.asyncio
    async def test_delete_missing_command_raises(self):
        remote = _make_remote()
        remote._codes = {"tv": {}}
        remote._storage_loaded = True
        with pytest.raises(ValueError, match="Command not found"):
            await remote.async_delete_command(command=["missing"], device="tv")

    @pytest.mark.asyncio
    async def test_delete_partial_missing_logs_error(self):
        remote = _make_remote()
        remote._codes = {"tv": {"power": "CODE"}}
        remote._storage_loaded = True
        # "power" exists, "missing" does not — partial failure, no raise
        await remote.async_delete_command(command=["power", "missing"], device="tv")
        assert "power" not in remote._codes.get("tv", {})


class TestAsyncLearnCommand:
    @pytest.mark.asyncio
    async def test_learn_ir_command(self):
        remote = _make_remote()
        remote._storage_loaded = True
        remote._receive_dp.get_value.side_effect = [None, "LEARNED_CODE"]

        with patch("custom_components.tuya_local.remote.persistent_notification"):
            with patch(
                "custom_components.tuya_local.remote.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                await remote.async_learn_command(
                    command=["power"], device="tv", alternative=False
                )

        assert remote._codes["tv"]["power"] == "LEARNED_CODE"
        remote._code_storage.async_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_learn_timeout_raises(self):
        remote = _make_remote()
        remote._storage_loaded = True
        remote._receive_dp.get_value.return_value = None

        with patch("custom_components.tuya_local.remote.persistent_notification"):
            with patch(
                "custom_components.tuya_local.remote.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                with patch(
                    "custom_components.tuya_local.remote.dt_util.utcnow"
                ) as mock_now:
                    from datetime import datetime, timedelta

                    start = datetime(2026, 1, 1)
                    # First call returns start, then jumps past timeout
                    mock_now.side_effect = [
                        start,
                        start,
                        start + timedelta(seconds=31),
                    ]
                    with pytest.raises(TimeoutError):
                        await remote.async_learn_command(
                            command=["power"], device="tv", alternative=False
                        )


class TestAsyncLoadStorage:
    @pytest.mark.asyncio
    async def test_load_storage(self):
        remote = _make_remote()
        remote._code_storage.async_load.return_value = {"tv": {"power": "CODE"}}
        remote._flag_storage.async_load.return_value = {"tv": 1}
        await remote._async_load_storage()
        assert remote._storage_loaded is True
        assert remote._codes == {"tv": {"power": "CODE"}}
        assert remote._flags["tv"] == 1

    @pytest.mark.asyncio
    async def test_load_empty_storage(self):
        remote = _make_remote()
        remote._code_storage.async_load.return_value = None
        remote._flag_storage.async_load.return_value = None
        await remote._async_load_storage()
        assert remote._storage_loaded is True
        assert remote._codes == {}


def _make_subdevice_remote():
    """Create a TuyaLocalRemote that represents a gateway sub-device.

    The parent hub TuyaLocalDevice is wired into hass.data[DOMAIN] so the
    routing logic in async_send_command and _async_learn_command can resolve
    it.
    """
    remote = _make_remote()

    parent_device = MagicMock()
    parent_device._name = "Parent Hub"
    parent_device.async_set_properties = AsyncMock()
    parent_device.async_refresh = AsyncMock()
    parent_device.anticipate_property_value = MagicMock()

    # Mark remote._device as a sub-device
    remote._device.dev_cid = "sub_device_cid"
    remote._device.dev_id = "hub_device_id"

    # Wire parent into hass.data[DOMAIN]
    domain_data = {
        "hub_device_id": {"device": parent_device},
    }
    remote._device._hass.data = {DOMAIN: domain_data}

    return remote, parent_device


class TestAsyncSendCommandSubdevice:
    """Tests for Bug 3: RF send must be routed via the parent hub on sub-devices."""

    @pytest.mark.asyncio
    async def test_rf_send_on_subdevice_routes_via_parent(self):
        """rfstudy_send for a sub-device must go through the parent hub."""
        remote, parent_device = _make_subdevice_remote()
        remote._storage_loaded = True
        remote._codes = {"gate_cid": {"power": "rf:BASE64CODE"}}

        await remote.async_send_command(
            ["power"], device="gate_cid", num_repeats=1
        )

        parent_device.async_set_properties.assert_awaited_once()
        remote._device.async_set_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ir_send_on_subdevice_uses_subdevice(self):
        """IR send_command on a sub-device must NOT reroute to the parent hub."""
        remote, parent_device = _make_subdevice_remote()
        remote._storage_loaded = True
        remote._codes = {"tv_cid": {"vol_up": "IR_CODE"}}

        await remote.async_send_command(
            ["vol_up"], device="tv_cid", num_repeats=1
        )

        remote._device.async_set_properties.assert_awaited_once()
        parent_device.async_set_properties.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rf_send_standalone_uses_own_device(self):
        """RF send on a standalone hub (no dev_cid) must not reroute."""
        remote = _make_remote()
        remote._storage_loaded = True
        remote._codes = {"gate": {"power": "rf:BASE64CODE"}}
        # dev_cid is None (set in _make_remote) — standalone hub

        await remote.async_send_command(
            ["power"], device="gate", num_repeats=1
        )

        remote._device.async_set_properties.assert_awaited_once()


class TestAsyncLearnCommandRfSubdevice:
    """Tests for Bug 1: RF learn must poll dp202 via the parent hub on sub-devices."""

    @pytest.mark.asyncio
    async def test_rf_learn_on_subdevice_sends_study_via_parent(self):
        """For a sub-device, rf_study must be sent on the parent hub connection."""
        remote, parent_device = _make_subdevice_remote()
        remote._storage_loaded = True
        remote._receive_dp.get_value.side_effect = [None, "RF_CODE"]

        with patch("custom_components.tuya_local.remote.persistent_notification"):
            with patch(
                "custom_components.tuya_local.remote.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                await remote.async_learn_command(
                    command=["gate"],
                    device="gate_cid",
                    alternative=False,
                    command_type="rf",
                )

        sent_to = [
            call.args[0] for call in remote._send_dp.async_set_value.call_args_list
        ]
        for dev in sent_to:
            assert dev is parent_device, (
                "rf_study / rfstudy_exit must be sent via the parent hub"
            )

    @pytest.mark.asyncio
    async def test_rf_learn_on_subdevice_polls_parent_for_dp202(self):
        """dp202 get_value must be called with the parent hub device, not the sub-device."""
        remote, parent_device = _make_subdevice_remote()
        remote._storage_loaded = True
        remote._receive_dp.get_value.side_effect = [None, "RF_CODE"]

        with patch("custom_components.tuya_local.remote.persistent_notification"):
            with patch(
                "custom_components.tuya_local.remote.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                await remote.async_learn_command(
                    command=["gate"],
                    device="gate_cid",
                    alternative=False,
                    command_type="rf",
                )

        # Every get_value call must use the parent hub, not the sub-device
        for call in remote._receive_dp.get_value.call_args_list:
            assert call.args[0] is parent_device, (
                "dp202 polling must target the parent hub, not the sub-device"
            )
        assert remote._receive_dp.get_value.call_count >= 1

    @pytest.mark.asyncio
    async def test_ir_learn_on_subdevice_still_uses_subdevice(self):
        """IR learning on a sub-device must NOT reroute to the parent hub."""
        remote, parent_device = _make_subdevice_remote()
        remote._storage_loaded = True
        remote._receive_dp.get_value.side_effect = [None, "IR_CODE"]

        with patch("custom_components.tuya_local.remote.persistent_notification"):
            with patch(
                "custom_components.tuya_local.remote.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                await remote.async_learn_command(
                    command=["power"], device="tv_cid", alternative=False
                )

        sent_to = [
            call.args[0] for call in remote._send_dp.async_set_value.call_args_list
        ]
        for dev in sent_to:
            assert dev is remote._device
        parent_device.async_refresh.assert_not_awaited()
