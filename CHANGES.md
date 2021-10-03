# Changelog for olmappy

## Version 1.1 (2021-10-03)

* Added `EXPORTLIST` and `HIDEIMPORT` commands to save, restore and transfer the list of hidden maps.
* Provide a file `outdatedMaps.json` which can be used with `HIDEIMPORT` to hide known outdated versions of maps which are superseeded by newer versions.
* Add option `--reverse` for `HIDEIMPORT` to reverse the hidden state from the import file.
* Add config options `verifyCertificates` and `certificateBundle` to allow manually controlling the TLS certfiticate validation when connecting via HTTPS.
* Improve map name output.

## Version 1.0 (2021-09-16)

* Initial release, basic map download and validation is working.

