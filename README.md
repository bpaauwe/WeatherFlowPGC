
# weatherflow-polyglot

This is the WeatherFlow Poly for the [Universal Devices ISY994i](https://www.universal-devices.com/residential/ISY) [Polyglot interface](http://www.universal-devices.com/developers/polyglot/docs/) with  [Polyglot V2](https://github.com/Einstein42/udi-polyglotv2)
(c) 2018 Robert Paauwe
MIT license.

This node server is intended to support the [WeatherFlow Smart Weather Station](http://www.weatherflow.com/).

## Installation

1. Backup Your ISY in case of problems!
   * Really, do the backup, please
2. Go to the Polyglot Store in the UI and install.
3. Add NodeServer in Polyglot Web
   * After the install completes, Polyglot will reboot your ISY, you can watch the status in the main polyglot log.
4. Once your ISY is back up open the Admin Console.
5. Configure the node server with your station ID.

### Node Settings
The settings for this node are:

#### Short Poll
   * This is how often it will update the last update time for each node.
#### Long Poll
   * Query WeatherFlow server for observation data
   * Sends a heartbeat as DON/DOF


## Requirements

1. Polyglot V2 itself should be run on Raspian Stretch.
  To check your version, ```cat /etc/os-release``` and the first line should look like
  ```PRETTY_NAME="Raspbian GNU/Linux 9 (stretch)"```. It is possible to upgrade from Jessie to
  Stretch, but I would recommend just re-imaging the SD card.  Some helpful links:
   * https://www.raspberrypi.org/blog/raspbian-stretch/
   * https://linuxconfig.org/raspbian-gnu-linux-upgrade-from-jessie-to-raspbian-stretch-9
2. This has only been tested with ISY 5.0.13 so it is not guaranteed to work with any other version.

# Upgrading

Open the Polyglot web page, go to nodeserver store and click "Update" for "WeatherFlow".

For Polyglot 2.0.35, hit "Cancel" in the update window so the profile will not be updated and ISY rebooted.  The install procedure will properly handle this for you.  This will change with 2.0.36, for that version you will always say "No" and let the install procedure handle it for you as well.

Then restart the WeatherFlow nodeserver by selecting it in the Polyglot dashboard and select Control -> Restart, then watch the log to make sure everything goes well.

The WeatherFlow nodeserver keeps track of the version number and when a profile rebuild is necessary.  The profile/version.txt will contain the WeatherFlow profile_version which is updated in server.json when the profile should be rebuilt.

# Release Notes

- 1.0.3 12/23/2019
   - On startup, set configured = true if stations is configured.
- 1.0.2 10/28/2019
   - Improve handling of custom parameters.
- 1.0.1 08/07/2019
   - Fix units for wind gust and lull
   - Handle missing station and add notice
   - Fix timestamp to really report time since last query
- 1.0.0 08/07/2019
   - Rewrite UOM handling and clean up profile files
   - Handle missing observation data properly
   - Handle both indoor and outdoor observations with priority given to outdoor
   - Only send data values when they change
- 0.0.1 12/27/2018
   - Initial version published to github
