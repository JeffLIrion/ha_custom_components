"""Support to track cast volume."""
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.const import ATTR_ENTITY_ID, CONF_NAME, EVENT_HOMEASSISTANT_START, SERVICE_VOLUME_MUTE, SERVICE_VOLUME_SET, STATE_IDLE, STATE_OFF, STATE_ON, STATE_PAUSED, STATE_PLAYING
from homeassistant.components.media_player.const import ATTR_MEDIA_VOLUME_LEVEL, ATTR_MEDIA_VOLUME_MUTED
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'cast_volume_tracker'
ENTITY_ID_FORMAT = DOMAIN + '.{}'

CAST_ON_STATES = (STATE_IDLE, STATE_PAUSED, STATE_PLAYING)

CONF_PARENTS = 'parents'
CONF_MEMBERS = 'members'
CONF_MEMBERS_EXCLUDED_WHEN_OFF = 'members_excluded_when_off'
CONF_MUTE_WHEN_OFF = 'mute_when_off'
CONF_DEFAULT_VOLUME_LEVEL = 'default_volume_level'


SERVICE_DEFAULT_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids
})

SERVICE_VOLUME_MUTE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_MEDIA_VOLUME_MUTED): cv.boolean,
})

SERVICE_VOLUME_SET_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Required(ATTR_MEDIA_VOLUME_LEVEL): vol.Coerce(float),
})


# =========================================================================== #
#                                                                             #
#                       Cast Volume Tracker (base class)                      #
#                                                                             #
# =========================================================================== #
class CastVolumeTracker(object):
    """A class for storing information about a cast device."""

    def __init__(self, cast_network, object_id, cast_is_on, value, is_volume_muted):
        self.cast_network = cast_network
        self.object_id = object_id

        # associated media player
        self.media_player = 'media_player.{0}'.format(object_id)

        self.cast_is_on = cast_is_on
        self.cast_volume_level = None

        self.is_volume_muted = is_volume_muted
        self.value = value

        self.cast_network.casts[object_id] = self

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return {'cast_is_on': self.cast_is_on,
                'value': self.value,
                'volume_level': self.cast_volume_level,
                'expected_volume_level': self.expected_volume_level,
                'is_volume_muted': self.is_volume_muted}

    @property
    def equilibrium(self):
        """Whether or not the cast volume is at the expected level."""
        return self.cast_volume_level is not None and round(self.cast_volume_level, 3) == round(self.expected_volume_level, 3)

    @property
    def expected_volume_level(self):
        """The expected cast volume level, based on ``self.value`` and ``self.is_volume_muted``."""
        return 0. if self.is_volume_muted else 0.01 * self.value

    def update(self, hass):
        """Update the cast volume tracker."""
        pass

    def set_attributes(self, cast_is_on=None, value=None, is_volume_muted=None):
        """Set the attributes for the cast volume tracker."""
        if cast_is_on is not None:
            self.cast_is_on = cast_is_on

        if value is not None:
            self.value = value

        if is_volume_muted is not None:
            self.is_volume_muted = is_volume_muted

    def volume_mute(self, is_volume_muted):
        """Mute/Un-mute the volume."""
        return []

    def volume_set(self, volume_level):
        """Set the volume."""
        return []


# =========================================================================== #
#                                                                             #
#                         Cast Volume Tracker (group)                         #
#                                                                             #
# =========================================================================== #
class CastVolumeTrackerGroup(CastVolumeTracker):
    """A class for storing information about a Chromecast group."""

    def __init__(self, cast_network, object_id, cast_is_on, value, is_volume_muted, members, members_excluded_when_off=None):
        super().__init__(cast_network, object_id, cast_is_on, value, is_volume_muted)

        # group members (i.e., object IDs)
        self.members = members
        if not members_excluded_when_off:
            self.members_when_off = members
        else:
            self.members_when_off = [member for member in members if member not in members_excluded_when_off]

        # cast volume trackers
        self.cast_volume_trackers = ['cast_volume_tracker.{0}'.format(member) for member in members]
        self.cast_volume_trackers_with_default = ['cast_volume_tracker.{0}'.format(member) for member in members if self.cast_network.casts[member].default_value is not None]
        self.cast_volume_trackers_without_default = ['cast_volume_tracker.{0}'.format(member) for member in members if self.cast_network.casts[member].default_value is None]

    def update(self, hass):
        """Update the cast volume tracker."""
        equilibrium = self.equilibrium
        cast_state_obj = hass.states.get(self.media_player)
        if cast_state_obj:
            cast_is_on = cast_state_obj.state in CAST_ON_STATES
            self.cast_volume_level = cast_state_obj.attributes.get('volume_level')
        else:
            return []

        if cast_is_on is None:
            return []

        # Off -> Off
        if not self.cast_is_on and not cast_is_on:
            return []

        # Off -> On
        if not self.cast_is_on and cast_is_on:
            return self._update_off_to_on()

        # On -> Off
        if self.cast_is_on and not cast_is_on:
            return self._update_on_to_off()

        if not equilibrium:
            return []

        # On -> On and volume changed
        if self.cast_volume_level is not None and round(self.expected_volume_level, 3) != round(self.cast_volume_level, 3):
            return self._update_on_to_on()

        return []

    def _update_off_to_on(self):
        self.cast_is_on = True
        self.is_volume_muted = False
        self.value = sum([self.cast_network.casts[member].value for member in self.members_when_off]) / len(self.members_when_off)

        # set the `cast_is_on` and `is_volume_muted` attributes for the speakers in the group
        for member in self.members:
            self.cast_network.casts[member].set_attributes(True, is_volume_muted=False)

        # 1) Set the cast volume tracker volumes
        return [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': self.cast_volume_trackers, 'volume_level': 0.01*self.value}]]

    def _update_on_to_off(self):
        self.cast_is_on = False
        self.is_volume_muted = True

        # set the `cast_is_on` and `is_volume_muted` attributes for the speakers in the group
        for member in self.members:
            self.cast_network.casts[member].set_attributes(False, is_volume_muted=self.cast_network.casts[member].mute_when_off)

        # 1) Set the cast volume tracker volumes for members without default values
        # 2) Set the cast volume tracker volumes for members with default values
        return [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': self.cast_volume_trackers_without_default, 'volume_level': 0.01*self.value}]] + [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': member,'volume_level': 0.01*self.cast_network.casts[member.replace('cast_volume_tracker.', '')].default_value}] for member in self.cast_volume_trackers_with_default]

    def _update_on_to_on(self):
        if all([self.cast_network.casts[member].is_volume_muted for member in self.members]):
            self.is_volume_muted = True
        else:
            self.is_volume_muted = False

        if not self.is_volume_muted:
            self.value = 100.*self.cast_volume_level * len(self.members) / sum([not self.cast_network.casts[member].is_volume_muted for member in self.members])

        # 1) Set the cast volume trackers
        return [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': self.cast_volume_trackers, 'volume_level': 0.01*self.value}]]

    def volume_mute(self, is_volume_muted):
        """Mute/Un-mute the volume for the group members."""
        if not self.cast_is_on:
            return []

        if is_volume_muted ^ self.is_volume_muted:
            self.set_attributes(is_volume_muted=is_volume_muted)

            # 1) Mute the cast volume trackers
            return [['cast_volume_tracker', SERVICE_VOLUME_MUTE, {'entity_id': self.cast_volume_trackers, 'is_volume_muted': is_volume_muted}]]

        return []

    def volume_set(self, volume_level):
        """Set the volume level for the group members."""
        if not self.cast_is_on:
            off_cast_volume_trackers = ['cast_volume_tracker.{0}'.format(member) for member in self.members_when_off if not self.cast_network.casts[member].cast_is_on]

            if not off_cast_volume_trackers:
                return []

            new_value = (100.*volume_level*len(off_cast_volume_trackers) + sum([self.cast_network.casts[member].value for member in self.members_when_off if self.cast_network.casts[member].cast_is_on])) / len(self.members_when_off)
            self.set_attributes(value=new_value)

            return [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': off_cast_volume_trackers, 'volume_level': volume_level}]]

        self.set_attributes(value=100.*volume_level)

        # 1) Set the cast volume tracker volumes
        return [['cast_volume_tracker', SERVICE_VOLUME_SET, {'entity_id': self.cast_volume_trackers, 'volume_level': volume_level}]]


# =========================================================================== #
#                                                                             #
#                       Cast Volume Tracker (individual)                      #
#                                                                             #
# =========================================================================== #
class CastVolumeTrackerIndividual(CastVolumeTracker):
    """A class for storing information about an individual Chromecast speaker."""

    def __init__(self, cast_network, object_id, cast_is_on, value, is_volume_muted, parents=None, mute_when_off=True, default_volume_level=None):
        super().__init__(cast_network, object_id, cast_is_on, value, is_volume_muted)

        # groups to which this speaker belongs
        if parents is None:
            self.parents = []
        else:
            self.parents = parents

        # mute the volume when this speaker turns off
        self.mute_when_off = mute_when_off

        # the volume to which this speaker should be set when it turns off
        if default_volume_level is not None:
            self.default_value = 100.*default_volume_level
        else:
            self.default_value = None

    @property
    def parent_is_on(self):
        """Whether or not a parent group is playing."""
        return any([self.cast_network.casts[parent].cast_is_on for parent in self.parents])

    def update(self, hass):
        """Update the cast volume tracker."""
        cast_state_obj = hass.states.get(self.media_player)
        if cast_state_obj:
            cast_is_on = cast_state_obj.state in CAST_ON_STATES
            self.cast_volume_level = cast_state_obj.attributes.get('volume_level')
        else:
            return []

        # Parent is playing
        if self.parent_is_on:
            return []

        # State is unknown
        if cast_is_on is None:
            return []

        # Off -> Off
        if not self.cast_is_on and not cast_is_on:
            return []

        # Off -> On
        if not self.cast_is_on and cast_is_on:
            return self._update_off_to_on()

        # On -> Off
        if self.cast_is_on and not cast_is_on:
            return self._update_on_to_off()

        # On -> On, volume changed and parent is not playing
        if self.cast_volume_level is not None and round(self.expected_volume_level, 3) != round(self.cast_volume_level, 3) and not self.parent_is_on:
            return self._update_on_to_on()

        # On -> On, volume did not change or parent is playing
        return []

    def _update_off_to_on(self):
        self.cast_is_on = True
        self.is_volume_muted = False

        # 1) Set the media player volume
        return [['media_player', SERVICE_VOLUME_SET, {'entity_id': self.media_player, 'volume_level': self.expected_volume_level}]]

    def _update_on_to_off(self):
        self.cast_is_on = False
        self.is_volume_muted = self.mute_when_off

        if self.default_value is not None:
            self.value = self.default_value

        # 1) Set the media player volume
        return [['media_player', SERVICE_VOLUME_SET, {'entity_id': self.media_player, 'volume_level': self.expected_volume_level}]]

    def _update_on_to_on(self):
        if not self.is_volume_muted:
            self.value = 100.*self.cast_volume_level

        # 1) Set the media player volume
        return [['media_player', SERVICE_VOLUME_SET, {'entity_id': self.media_player, 'volume_level': self.expected_volume_level}]]

    def volume_mute(self, is_volume_muted):
        """Mute/Un-mute the volume."""
        if is_volume_muted ^ self.is_volume_muted:
            self.set_attributes(is_volume_muted=is_volume_muted)

            # 1) Set the media player volume
            return [['media_player', SERVICE_VOLUME_SET, {'entity_id': self.media_player, 'volume_level': self.expected_volume_level}]]

        return []

    def volume_set(self, volume_level):
        """Set the volume."""
        self.set_attributes(value=100.*volume_level)

        # 1) Set the media player volume
        return [['media_player', SERVICE_VOLUME_SET, {'entity_id': self.media_player, 'volume_level': self.expected_volume_level}]]

# =========================================================================== #
#                                                                             #
#                                Cast Network                                 #
#                                                                             #
# =========================================================================== #
class CastNetwork(object):
    """A class for tracking and controlling cast devices."""

    def __init__(self):
        self.casts = {}


CN = CastNetwork()


# =========================================================================== #
#                                                                             #
#                         Cast Volume Tracker setup                           #
#                                                                             #
# =========================================================================== #
def cvt_setup(object_id, members=None, parents=None, cast_is_on=None, value=0, is_volume_muted=None, mute_when_off=True, default_volume_level=None):
    if members:
        return CastVolumeTrackerGroup(CN, object_id, members, cast_is_on=cast_is_on, value=value, is_volume_muted=is_volume_muted)

    return CastVolumeTrackerIndividual(CN, object_id, parents, cast_is_on=cast_is_on, value=value, is_volume_muted=is_volume_muted)


def _cv_cast_volume_tracker(cfg):
    """Configure validation helper for Cast volume tracker."""
    return cfg


CONFIG_SCHEMA = vol.Schema({
    DOMAIN: cv.schema_with_slug_keys(
        vol.All({
            vol.Required(CONF_NAME): cv.string,
            vol.Optional(CONF_PARENTS, default=list()): cv.ensure_list,
            vol.Optional(CONF_MEMBERS): cv.ensure_list,
            vol.Optional(CONF_MEMBERS_EXCLUDED_WHEN_OFF, default=list()): cv.ensure_list,
            vol.Optional(CONF_MUTE_WHEN_OFF, default=True): cv.boolean,
            vol.Optional(CONF_DEFAULT_VOLUME_LEVEL): vol.Coerce(float)
        }, _cv_cast_volume_tracker)
    )
}, required=True, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up a cast volume tracker."""
    component = EntityComponent(_LOGGER, DOMAIN, hass)

    entities = []

    # setup individual speakers first
    for object_id, cfg in sorted(config[DOMAIN].items(), key=lambda x: CONF_MEMBERS in x[1]):
        name = cfg.get(CONF_NAME)

        cast_state_obj = hass.states.get('media_player.{0}'.format(object_id))
        if cast_state_obj:
            cast_is_on = cast_state_obj.state in CAST_ON_STATES
            cast_volume_level = cast_state_obj.attributes.get('volume_level')

            if cast_volume_level is not None:
                is_volume_muted = cast_volume_level > 1e-3
                value = 100.*cast_volume_level
            else:
                state = await self.async_get_last_state()

                if state.state is not None:
                    value = state.state
                else:
                    value = 100.*cfg[CONF_DEFAULT_VOLUME_LEVEL]

                if state.attributes.get('is_volume_muted') is not None:
                    is_volume_muted = state.attributes.get('is_volume_muted')
                else:
                    is_volume_muted = cfg[CONF_MUTE_WHEN_OFF]
        else:
            cast_is_on = False
            is_volume_muted = cfg[CONF_MUTE_WHEN_OFF]
            default_volume_level = cfg.get(CONF_DEFAULT_VOLUME_LEVEL)
            if default_volume_level is not None:
                value = 100.*default_volume_level
            else:
                value = 0.

        if CONF_MEMBERS not in cfg:
            entities.append(CastVolumeTrackerEntity(hass, object_id, name, CastVolumeTrackerIndividual(CN, object_id, cast_is_on, value, is_volume_muted, cfg[CONF_PARENTS], cfg[CONF_MUTE_WHEN_OFF], cfg.get(CONF_DEFAULT_VOLUME_LEVEL))))
        else:
            entities.append(CastVolumeTrackerEntity(hass, object_id, name, CastVolumeTrackerGroup(CN, object_id, cast_is_on, value, is_volume_muted, cfg[CONF_MEMBERS], cfg[CONF_MEMBERS_EXCLUDED_WHEN_OFF])))

    if not entities:
        return False

    component.async_register_entity_service(
        SERVICE_VOLUME_MUTE, SERVICE_VOLUME_MUTE_SCHEMA,
        'async_volume_mute'
    )

    component.async_register_entity_service(
        SERVICE_VOLUME_SET, SERVICE_VOLUME_SET_SCHEMA,
        'async_volume_set'
    )

    await component.async_add_entities(entities)
    return True


class CastVolumeTrackerEntity(RestoreEntity):
    """Representation of a Cast volume tracker."""

    def __init__(self, hass, object_id, name, cast_volume_tracker):
        """Initialize a Cast Volume Tracker."""
        self.hass = hass
        self.entity_id = ENTITY_ID_FORMAT.format(object_id)
        self._entities = ['media_player.{0}'.format(object_id)]
        self._name = name
        self._cast_volume_tracker = cast_volume_tracker

    @property
    def should_poll(self):
        """If entity should be polled."""
        return False

    @property
    def name(self):
        """Return the name of the cast volume tracker."""
        return self._name

    @property
    def state(self):
        """Return the state of the component."""
        return round(self._cast_volume_tracker.value, 2)

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return self._cast_volume_tracker.state_attributes

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass and register callbacks."""
        @callback
        def cast_volume_tracker_state_listener(entity, old_state, new_state):
            """Handle target device state changes."""
            self.async_schedule_update_ha_state(True)

        @callback
        def cast_volume_tracker_startup(event):
            """Listen for state changes."""
            if self._entities:
                async_track_state_change(self.hass, self._entities, cast_volume_tracker_state_listener)

            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, cast_volume_tracker_startup)

        await super().async_added_to_hass()

    async def async_volume_set(self, volume_level):
        """Set new volume level."""
        service_args = self._cast_volume_tracker.volume_set(volume_level)

        for args in service_args:
            await self.hass.services.async_call(*args)

        await self.async_update_ha_state()

    async def async_volume_mute(self, is_volume_muted):
        """Mute the volume."""
        service_args = self._cast_volume_tracker.volume_mute(is_volume_muted)

        for args in service_args:
            await self.hass.services.async_call(*args)

        await self.async_update_ha_state()

    async def async_update(self):
        """Update the state and perform any necessary service calls."""
        service_args = self._cast_volume_tracker.update(self.hass)

        for args in service_args:
            await self.hass.services.async_call(*args)
