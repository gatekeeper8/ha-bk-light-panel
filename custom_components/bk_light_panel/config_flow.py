"""Config flow: panels are found via Bluetooth, or entered by address."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_ADDRESS, DOMAIN

_LOGGER = logging.getLogger(__name__)

NAME_PREFIX = "LED_BLE_"
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
MANUAL = "manual"


class BkLightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a BK-Light panel."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name,
                data={CONF_ADDRESS: self._discovery.address.upper()},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    async def _create(self, address: str, title: str) -> ConfigFlowResult:
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data={CONF_ADDRESS: address})

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == MANUAL:
                return await self.async_step_manual()
            return await self._create(address, self._found.get(address, address))

        configured = self._async_current_ids(include_ignore=False)
        # look at everything HA has heard, not only "connectable" devices:
        # some proxies report the panel's advertisements as non-connectable
        for connectable in (True, False):
            for info in async_discovered_service_info(self.hass, connectable=connectable):
                address = info.address.upper()
                name = info.name or ""
                _LOGGER.debug(
                    "Seen %s %s connectable=%s source=%s", address, name, info.connectable, info.source
                )
                if name.startswith(NAME_PREFIX) and address not in configured:
                    self._found.setdefault(address, name)

        if not self._found:
            return await self.async_step_manual()
        choices = {addr: f"{name} ({addr})" for addr, name in self._found.items()}
        choices[MANUAL] = "Enter the address by hand"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            if MAC_RE.match(address):
                return await self._create(address, f"{NAME_PREFIX}{address.replace(':', '')[-8:]}")
            errors[CONF_ADDRESS] = "invalid_address"
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )
