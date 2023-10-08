# Plex Extras Collection

Plex Extras Collection is a quick-and-dirty port of [PlexCommentaryCollection](https://github.com/danrahn/PlexCommentaryCollection), creating a Plex collection for items in your library that have local extras associated with them.

## Requirements

Python 3 and the packages outlined in requirements.txt, which can be installed via `pip install -r requirements.txt`

## Usage

`python PlexExtrasCollection.py`

## Configuration
Configuration values can be specified in the command line or config.yml:

* `host`: The host of the Plex server. Defaults to http://localhost:32400
* `section`: The id of the library to scan. Defaults to 1
* `token`: Your Plex token. No default, must be provided
* `collection_name`: The name of the collection to add items to. Defaults to "Movies with Extras"
* `no_delete`: Don't remove items from the collection that don't have local extras

If values aren't provided, they'll be asked interactively when running the script.
