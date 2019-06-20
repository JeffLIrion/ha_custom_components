This repository contains 2 custom components:

* Cast Volume Tracker: allows you to track and control volume for Chromecast devices
* Input Number: this adds template functionality to the `input_number` component

It also contains an example configuration for these components in the [example_config](./example_config) folder, as well as some tests to check that the `cast_volume_tracker` component is working as expected.


## Cast Volume Tracker

This component does the following:

* When an individual speaker is off, by default its media player volume will be set to zero -- effectively muting it -- but its "desired" volume level will be retained
* When an individual speaker turns on, its volume level will be set to its desired volume level
  * As a result, you won't hear the "blip" noise when the device turns on
* When a group turns on, the volume for each of its members will be set to the average value of its members (excluding any members provided in its `members_excluded_when_off` parameter)
* During group playback, the volume of all of its members will be kept normalized

The idea is that for all your cast devices, you would setup a `cast_volume_tracker` and replace all `media_player.volume_set` service calls with `cast_volume_tracker.volume_set`.  The usage is the same, except that the entity ID should be for the `cast_volume_tracker` instead of the `media_player` (i.e., `cast_volume_tracker.computer_speakers` instead of `media_player.computer_speakers`).


### Example configuration:

**NOTE:** the names *must* correspond to the names of your cast devices.  In other words, `cast_volume_tracker.computer_speakers` will correspond to `media_player.computer_speakers`.

```yaml
# individual speaker
computer_speakers:
  name: 'Computer Speakers'
  parents:
  - kitchen_speakers

# individual speaker
kitchen_home:
  name: 'Kitchen Home'
  mute_when_off: false
  default_volume_level: 0.16
  parents:
  - kitchen_speakers

# cast group
kitchen_speakers:
  name: 'Kitchen Speakers'
  members:
  - computer_speakers
  - kitchen_home
  members_excluded_when_off:
  - kitchen_home
```

For an individual cast device, the configuration variables are:

* **name** (required): friendly name for the cast volume tracker
* **parents** (optional): groups to which the cast device belongs
* **mute_when_off** (optional, default=`true`): if `true`, when the cast device turns off the volume will be set to 0, effectively muting it; if `false`, the volume will be set to `default_volume_level` (if provided) or left as is
* **default_volume_level** (optional): if provided, the volume for the cast device will be set to this level when the cast is turned off
* **off_script**: a script or sequence of actions to perform when the speaker turns off
* **on_script**: a script or sequence of actions to perform when the speaker turns on

When the configuration variable `members` is provided, the cast volume tracker will be recognized as a group.  For cast groups, the configuration variables are:

* **name** (required): friendly name for the cast volume tracker
* **members**: the object ID's of the group members (e.g., `kitchen_home` for `media_player.kitchen_home`)
* **members_excluded_when_off** (optional): when turning the group on, the volume for all speakers will be set to the average of the values of the cast volume trackers *not* included in this list
* **off_script**: a script or sequence of actions to perform when the speaker turns off
* **on_script**: a script or sequence of actions to perform when the speaker turns on

The file [switches.yaml](./example_config/switches.yaml) demonstrates how to create switches for muting/un-muting `cast_volume_tracker` entities.


## Input Number

This component is to the built-in [`input_number`](https://www.home-assistant.io/components/input_number/) what a template switch is to an input boolean.  It accomplishes two things:

1. Its value can track other entities by way of a template.
2. When its value is changed, it can run a script.

In addition to the parameters for a standard [`input_number`](https://www.home-assistant.io/components/input_number/), its configuration variables are:

* **set_value_script**: a script or sequence of actions to perform when changing the value
* **value_template**: a template that will provide the state for the `input_number`
* **icon_template**: a template for this entity's icon
* **entity_id**: a list of entity ID's involved in the `value_template` and `icon_template` templates
* **value_changed_script**: a script or sequence of actions that will be performed when `value_template` changes (but not when `input_number.set_value` or `input_number.set_value_no_script` are called); the new value will be provided as the variable `value`


### Example Configuration

The file [input_numbers.yaml](./example_config/input_numbers.yaml) demonstrates how to setup `input_number`s that will track the value of a `cast_volume_tracker` when its state changes and change the value of a `cast_volume_tracker` when its value is changed.
