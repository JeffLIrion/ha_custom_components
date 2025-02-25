"""Support to set a numeric value from a slider or text box."""
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_UNIT_OF_MEASUREMENT, CONF_ICON, CONF_NAME, CONF_MODE)
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.restore_state import RestoreEntity

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'input_number'
ENTITY_ID_FORMAT = DOMAIN + '.{}'

CONF_INITIAL = 'initial'
CONF_MIN = 'min'
CONF_MAX = 'max'
CONF_STEP = 'step'

MODE_SLIDER = 'slider'
MODE_BOX = 'box'

ATTR_INITIAL = 'initial'
ATTR_VALUE = 'value'
ATTR_MIN = 'min'
ATTR_MAX = 'max'
ATTR_STEP = 'step'
ATTR_MODE = 'mode'

SERVICE_SET_VALUE = 'set_value'
SERVICE_INCREMENT = 'increment'
SERVICE_DECREMENT = 'decrement'

SERVICE_DEFAULT_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids
})

SERVICE_SET_VALUE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_VALUE): vol.Coerce(float),
})


def _cv_input_number(cfg):
    """Configure validation helper for input number (voluptuous)."""
    minimum = cfg.get(CONF_MIN)
    maximum = cfg.get(CONF_MAX)
    if minimum >= maximum:
        raise vol.Invalid('Maximum ({}) is not greater than minimum ({})'
                          .format(minimum, maximum))
    state = cfg.get(CONF_INITIAL)
    if state is not None and (state < minimum or state > maximum):
        raise vol.Invalid('Initial value {} not in range {}-{}'
                          .format(state, minimum, maximum))
    return cfg


# =========================================================================== #
#                                                                             #
#                              Template Number                                #
#                                                                             #
# =========================================================================== #
from homeassistant.core import callback
from homeassistant.const import (
    CONF_ENTITY_ID, CONF_ICON_TEMPLATE, CONF_VALUE_TEMPLATE, EVENT_HOMEASSISTANT_START, MATCH_ALL)
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.script import Script


CONF_SET_VALUE_SCRIPT = 'set_value_script'
CONF_VALUE_CHANGED_SCRIPT = 'value_changed_script'

SERVICE_SET_VALUE_NO_SCRIPT = 'set_value_no_script'


def _cv_template_number(cfg):
    """Configure validation helper for template number (voluptuous)."""
    _cv_input_number(cfg)

    if CONF_VALUE_TEMPLATE in cfg and not CONF_SET_VALUE_SCRIPT in cfg:
        raise vol.Invalid('{} cannot be provided without {}'.format(CONF_VALUE_TEMPLATE, CONF_SET_VALUE_SCRIPT))

    return cfg


CONFIG_SCHEMA = vol.Schema({
    DOMAIN: cv.schema_with_slug_keys(
        vol.All({
            vol.Optional(CONF_NAME): cv.string,
            vol.Required(CONF_MIN): vol.Coerce(float),
            vol.Required(CONF_MAX): vol.Coerce(float),
            vol.Optional(CONF_INITIAL): vol.Coerce(float),
            vol.Optional(CONF_STEP, default=1):
                vol.All(vol.Coerce(float), vol.Range(min=1e-3)),
            vol.Optional(CONF_ICON): cv.icon,
            vol.Optional(ATTR_UNIT_OF_MEASUREMENT): cv.string,
            vol.Optional(CONF_MODE, default=MODE_SLIDER):
                vol.In([MODE_BOX, MODE_SLIDER]),
            # TemplateNumber
            vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
            vol.Optional(CONF_SET_VALUE_SCRIPT): cv.SCRIPT_SCHEMA,
            vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_ICON_TEMPLATE): cv.template,
            vol.Optional(CONF_VALUE_CHANGED_SCRIPT): cv.SCRIPT_SCHEMA
        }, _cv_template_number)
    )
}, required=True, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up an input slider."""
    component = EntityComponent(_LOGGER, DOMAIN, hass)

    entities = []

    for object_id, cfg in config[DOMAIN].items():
        name = cfg.get(CONF_NAME)
        minimum = cfg.get(CONF_MIN)
        maximum = cfg.get(CONF_MAX)
        initial = cfg.get(CONF_INITIAL)
        step = cfg.get(CONF_STEP)
        icon = cfg.get(CONF_ICON)
        unit = cfg.get(ATTR_UNIT_OF_MEASUREMENT)
        mode = cfg.get(CONF_MODE)

        # Template Number
        if CONF_SET_VALUE_SCRIPT in cfg:
            icon_template = cfg.get(CONF_ICON_TEMPLATE)
            set_value_script = cfg.get(CONF_SET_VALUE_SCRIPT)
            value_template = cfg.get(CONF_VALUE_TEMPLATE)
            value_changed_script = cfg.get(CONF_VALUE_CHANGED_SCRIPT)

            # setup the entity ID's for the template
            template_entity_ids = set()
            if value_template is not None:
                temp_ids = value_template.extract_entities()
                if str(temp_ids) != MATCH_ALL:
                    template_entity_ids |= set(temp_ids)

            if icon_template is not None:
                icon_ids = icon_template.extract_entities()
                if str(icon_ids) != MATCH_ALL:
                    template_entity_ids |= set(icon_ids)

            entity_ids = cfg.get(CONF_ENTITY_ID, template_entity_ids)

            # Template Number
            entities.append(TemplateNumber(
                object_id, name, initial, minimum, maximum, step, icon,
                icon_template, unit, mode, hass, value_template,
                set_value_script, entity_ids, value_changed_script))

            continue

        entities.append(InputNumber(
            object_id, name, initial, minimum, maximum, step, icon, unit,
            mode))

    if not entities:
        return False

    component.async_register_entity_service(
        SERVICE_SET_VALUE, SERVICE_SET_VALUE_SCHEMA,
        'async_set_value'
    )

    component.async_register_entity_service(
        SERVICE_INCREMENT, SERVICE_DEFAULT_SCHEMA,
        'async_increment'
    )

    component.async_register_entity_service(
        SERVICE_DECREMENT, SERVICE_DEFAULT_SCHEMA,
        'async_decrement'
    )

    component.async_register_entity_service(
        SERVICE_SET_VALUE_NO_SCRIPT, SERVICE_SET_VALUE_SCHEMA,
        'async_set_value_no_script'
    )

    await component.async_add_entities(entities)
    return True


class InputNumber(RestoreEntity):
    """Representation of a slider."""

    def __init__(self, object_id, name, initial, minimum, maximum, step, icon,
                 unit, mode):
        """Initialize an input number."""
        self.entity_id = ENTITY_ID_FORMAT.format(object_id)
        self._name = name
        self._current_value = initial
        self._initial = initial
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._icon = icon
        self._unit = unit
        self._mode = mode

    @property
    def should_poll(self):
        """If entity should be polled."""
        return False

    @property
    def name(self):
        """Return the name of the input slider."""
        return self._name

    @property
    def icon(self):
        """Return the icon to be used for this entity."""
        return self._icon

    @property
    def state(self):
        """Return the state of the component."""
        return self._current_value

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_INITIAL: self._initial,
            ATTR_MIN: self._minimum,
            ATTR_MAX: self._maximum,
            ATTR_STEP: self._step,
            ATTR_MODE: self._mode,
        }

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if self._current_value is not None:
            return

        state = await self.async_get_last_state()
        value = state and float(state.state)

        # Check against None because value can be 0
        if value is not None and self._minimum <= value <= self._maximum:
            self._current_value = value
        else:
            self._current_value = self._minimum

    async def async_set_value(self, value):
        """Set new value."""
        num_value = float(value)
        if num_value < self._minimum or num_value > self._maximum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            num_value, self._minimum, self._maximum)
            return
        self._current_value = num_value
        await self.async_update_ha_state()

    async def async_increment(self):
        """Increment value."""
        new_value = self._current_value + self._step
        if new_value > self._maximum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            new_value, self._minimum, self._maximum)
            return
        self._current_value = new_value
        await self.async_update_ha_state()

    async def async_decrement(self):
        """Decrement value."""
        new_value = self._current_value - self._step
        if new_value < self._minimum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            new_value, self._minimum, self._maximum)
            return
        self._current_value = new_value
        await self.async_update_ha_state()

    async def async_set_value_no_script(self, value):
        """Set new value."""
        num_value = float(value)
        if num_value < self._minimum or num_value > self._maximum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            num_value, self._minimum, self._maximum)
            return
        self._current_value = num_value
        await self.async_update_ha_state()


class TemplateNumber(InputNumber):
    """Representation of a slider with template functionality."""

    def __init__(self, object_id, name, initial, minimum, maximum, step, icon,
                 icon_template, unit, mode, hass, value_template,
                 set_value_script, entity_ids, value_changed_script):
        """Initialize a template number."""
        super().__init__(object_id, name, initial, minimum, maximum, step,
                         icon, unit, mode)
        self.hass = hass
        self._entities = entity_ids

        # template
        self._value_template = value_template
        if self._value_template is not None:
            self._value_template.hass = self.hass

        # icon template
        self._icon_template = icon_template
        if self._icon_template is not None:
            self._icon_template.hass = self.hass

        # set_value_script
        if set_value_script:
            self._set_value_script = Script(hass, set_value_script)
        else:
            self._set_value_script = None

        # value_changed_script
        if value_changed_script:
            self._value_changed_script = Script(hass, value_changed_script)
        else:
            self._value_changed_script = None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass and register callbacks."""
        @callback
        def template_number_state_listener(entity, old_state, new_state):
            """Handle target device state changes."""
            self.async_schedule_update_ha_state(True)

        @callback
        def template_number_startup(event):
            """Listen for state changes."""
            if self._entities:
                async_track_state_change(
                    self.hass, self._entities, template_number_state_listener)

            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, template_number_startup)

        await super().async_added_to_hass()
        if self._current_value is not None:
            return

        state = await self.async_get_last_state()
        value = state and float(state.state)

        # Check against None because value can be 0
        if value is not None and self._minimum <= value <= self._maximum:
            self._current_value = value
        else:
            self._current_value = self._minimum

    async def async_set_value(self, value):
        """Set new value."""
        num_value = float(value)
        if num_value < self._minimum or num_value > self._maximum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            num_value, self._minimum, self._maximum)
            return
        self._current_value = num_value

        if self._set_value_script:
            await self._set_value_script.async_run(
                {"value": self._current_value}, context=self._context)
        await self.async_update_ha_state()

    async def async_increment(self):
        """Increment value."""
        new_value = self._current_value + self._step
        if new_value > self._maximum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            new_value, self._minimum, self._maximum)
            return
        self._current_value = new_value

        if self._set_value_script:
            await self._set_value_script.async_run(
                {"value": self._current_value}, context=self._context)

        await self.async_update_ha_state()

    async def async_decrement(self):
        """Decrement value."""
        new_value = self._current_value - self._step
        if new_value < self._minimum:
            _LOGGER.warning("Invalid value: %s (range %s - %s)",
                            new_value, self._minimum, self._maximum)
            return
        self._current_value = new_value

        if self._set_value_script:
            await self._set_value_script.async_run(
                {"value": self._current_value}, context=self._context)

        await self.async_update_ha_state()

    async def async_update(self):
        """Update the state from the template."""
        if self._value_template:
            try:
                value = self._value_template.async_render()
                if value not in ['None', 'unknown'] and self._current_value != float(value):
                    self._current_value = float(value)

                    if self._value_changed_script:
                        await self._value_changed_script.async_run(
                            {"value": self._current_value}, context=self._context)

            except TemplateError as ex:
                _LOGGER.error(ex)

        if self._icon_template:
            try:
                setattr(self, '_icon', self._icon_template.async_render())
            except TemplateError as ex:
                if ex.args and ex.args[0].startswith(
                        "UndefinedError: 'None' has no attribute"):
                    # Common during HA startup - so just a warning
                    _LOGGER.warning('Could not render icon template for %s, the state is unknown.', self._name)
