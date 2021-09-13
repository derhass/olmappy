# olmappy
Simple python script for Overload map management. Meant to connect to https://overloadmaps.com

### USAGE:

```
usage: olmap.py [-h] [-s NAME VALUE] [-n NAME] [-f FILENAME] [-t TYPE]
                [-b DATETIME] [-a DATETIME] [-A]
                [operation]

Manage Overload maps.

positional arguments:
  operation             the operation to execute, must be one of: IMPORT,
                        UPDATE, LISTLOCAL, LISTREMOTE, HIDE, UNHIDE,
                        WRITECONFIG. Default is UPDATE.

optional arguments:
  -h, --help            show this help message and exit
  -s NAME VALUE, --set NAME VALUE
                        set configuration option NAME to VALUE
  -n NAME, --name NAME  add filter for map name
  -f FILENAME, --filename FILENAME
                        add filter for map filename
  -t TYPE, --type TYPE  add filter for map type
  -b DATETIME, --time-before DATETIME
                        add filter for map mtime: must be before given
                        DATETIME
  -a DATETIME, --time-after DATETIME
                        add filter for map mtime: must be at or after given
                        DATETIME
  -A, --all             for HIDE or UNHIDE operations, when no filter is
                        specified: really apply to ALL maps
```

#### OPERATIONS:

The `OPERATION`s are:
* `IMPORT`: Import all files in the map directory into the olmappy index be checking with the server. If the `removeUnknownMaps` setting is enabled, maps which are not found on the server are moved into the `replaced` sub-directory and are deactivated. If the `autoImport` setting is enabled, the `IMPORT` step is done at every `UPDATE`, too.
* `UPDATE`: Retrieve the map list from the server and download all new maps, or update existing ones. If two maps with the same filename exist on the server, the newer one will be used.
* `LISTLOCAL`: List all locally stored maps (known to olmappy).
* `LISTREMOTE`: List all corrently stored maps on the server.
* `HIDE`: Hide maps from the game. A hidden map may still be updated, but stays hidden.
* 'UNHIDE': Unhide hidden maps so that hey are seen in the game.
* 'WRITECONFIG`: Write the config file. This is useful for initally populating the config file, and may be combined with several `--set` parameters to specify config values.

#### CONFIGURATION:

The following configuration values are present:
* `mapPath`: The path to the Overload maps, default: `/usr/share/Revival/Overload/`. Note that this path may not be writable by the user by default. You have been warned.
* `mapServer`: The map server, default: `https://overloadmaps.com`.
* 'mapServerListURL`: The URL of the JSON map list on the server, default: `/data/all.json`.
* `logLevel`: Controls the verbosity from 0 (only errors) to 3 (debug messages), default: `2` (information).
* `filenameCaseSensitive`: Treat filenames as case sensitive, default: `False` for compatibility with Windows.
* `filterCaseSensitive`: Treat name and filename filters as case sensitive, default: `False` for convenience.
* `removeUnknownMaps`: When importing maps, remove all not present on the server, default: `False`.
* `autoImport`: Before updating, also run import, default: `True`.
* `configFile`: The path to the configuration file, default: `$HOME/.config/olmappy.json`. This option is not written to the configfile, it is only used via `--set` to specify the location of the config file for laoding / writing.

Use `WRITECONFIG` to generate the initial config file, and edit the values as you please.

#### FILTERS:

* The filters `--name` or `--filename` accept strings and will match any substring in the map name / map filename.
* The `--type` filter can be `SP`, `MP`, or `CM` for Single-Player, Multi-Player, or Challene-Mode maps, respectively. The case of the letters does not matter. Note that a single map file can and typically does contain maps for different types. If the filter matches any type of such an archive file, it will apply to the whole file, not the sub-maps in it.
* The `--time-before` and `--time-after` filters take a date and time in the form `YEAR-MONTH-DAY HOUR:MINUTE:SECOND` or `YEAR-MONTH-DAY` (for midnight at that point in time).
* The `--all` option must be given for `HIDE` or `UNHIDE` operations if you otherwise did not specify any filters and what to operate on all maps.

If multiple filters of the same category are combined, the are treated as an `OR` operation. The time filters cannot be specified multiple times, the last one of each kind is effective.

#### EXAMPLES:

To update the maps from the server, use:
```
olmap.py UPDATE
```

To list only the locally available challenge mode maps, use:
```
olmap.py LISTLOCAL --type CM
```

To list all Multiplayer maps containing and `ro` or `bs` in their name, and which are from 2021 or newer, on the server, use:
```
olmap.py LISTREMOTE --type mp --name ro --name bs --time-after 2021-01-01
```

To initalize the config file with the default values (assuming no config file already exists, otherthise the values in it will be used), use:
```
olmap.py WRITECONFIG
```

To hide a map you don't like:
```
olmap.py HIDE -n skull
```

To unhide all currently hidden maps:
```
olmap.py UNHIDE --all
```

Have fun,
     derhass
     (<derhass@arcor.de>)

