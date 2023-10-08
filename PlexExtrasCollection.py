import math
import os
import requests
import time
import urllib
import yaml
import argparse
import sys
from urllib import parse
import json


class CommentaryCollection:
    def __init__(self):
        self.get_config()
        self.mediaItems = {}


    def get_config(self):
        """Reads the config file from disk

        Required parameters:
            token - your Plex token

        Optional (but strongly encouraged):
            host: the host of your plex server. Defaults to localhost:32400 if not provided
            library_section: The library you want to parse for commentary tracks. Default to 1 if not provided
            collection_name: The name of the collection. Defaults to "Movies with Extras" if not provided
        """

        self.valid = False
        config_file = self.adjacent_file('config.yml')
        if not os.path.exists(config_file):
            print('Could not find config.yml! Make sure it\'s in the same directory as this script')
            return

        config = None
        with open(config_file) as f:
            config = yaml.load(f, Loader=yaml.SafeLoader)

        if not config:
            config = {}

        parser = argparse.ArgumentParser()
        parser.add_argument('-p', '--host', help='Plex host')
        parser.add_argument('-t', '--token', help='Your Plex token')
        parser.add_argument('-s', '--section', help='Library section to scan')
        parser.add_argument('-c', '--collection', help='Collection name')
        parser.add_argument('-nd', '--no_delete', action='store_true', help='Don\'t delete items in the collection that have no local extras.')

        cmd_args = parser.parse_args()
        self.token = self.get_config_value(config, cmd_args, 'token', prompt='Enter your Plex token')
        self.host = self.get_config_value(config, cmd_args, 'host', default='http://localhost:32400')
        self.section_id = self.get_config_value(config, cmd_args, 'section', default=None)
        if isinstance(self.section_id, str) and self.section_id.isnumeric():
            self.section_id = int(self.section_id)
        self.collection_name = self.get_config_value(config, cmd_args, 'collection', default='Movies with Extras')
        self.no_delete = self.get_config_value(config, cmd_args, 'no_delete', default=False)

        self.section_type = "movie"

        self.valid = True


    def get_config_value(self, config, cmd_args, key, default='', prompt=''):
        cmd_arg = None
        if key in cmd_args:
            cmd_arg = cmd_args.__dict__[key]

        if key in config and config[key] != None:
            if cmd_arg != None:
                # Command-line args shadow config file
                print(f'WARN: Duplicate argument "{key}" found in both command-line arguments and config file. Using command-line value ("{cmd_args.__dict__[key]}")')
                return cmd_arg
            return config[key]

        if cmd_arg != None:
            return cmd_arg

        if default == None:
            return ''

        if len(default) != 0:
            return default

        if len(prompt) == 0:
            return input(f'\nCould not find "{key}" and no default is available.\n\nPlease enter a value for "{key}": ')
        return input(f'\n{prompt}: ')


    def run(self):
        """Kick off the processing"""

        if not self.valid:
            return

        if not self.test_plex_connection():
            return

        self.get_section()

        root = self.get_all_items()
        if not root:
            return

        item_count = len(root)
        print(f'Found {item_count} items to parse')
        processed = 0
        start = time.time()
        update_interval = 2
        next_update = update_interval
        groups = [root[i:min(item_count, i + 50)] for i in range(0, item_count, 50)]
        print(f'Breaking into {len(groups)} groups for parsing')
        for group in groups:
            processed += 1

            self.process_item_group(group)

            end = time.time()
            if (math.floor(end - start) >= next_update):
                next_update += update_interval
                print(f'Processed {processed} of {len(groups)} ({((processed / len(groups)) * 100):.2f}%) in {(end - start):.1f} seconds')

        print(f'\nDone! Processed {processed} movie{"" if item_count == 1 else "s"} in {time.time() - start:.2f} seconds')
        self.post_process()


    def test_plex_connection(self):
        """
        Does some basic validation to ensure we get a valid response from Plex with the given
        host and token.
        """

        status = None
        try:
            status = requests.get(self.url('/')).status_code
        except requests.exceptions.ConnectionError:
            print(f'Unable to connect to {self.host} ({sys.exc_info()[0].__name__}), exiting...')
            return False
        except:
            print(f'Something went wrong when connecting to Plex ({sys.exc_info()[0].__name__}), exiting...')
            return False

        if status == 200:
            return True

        if status == 401 or status == 403:
            print('Could not connect to Plex with the provided token, exiting...')
        else:
            print(f'Bad response from Plex ({status}), exiting...')
        return False


    def get_section(self):
        """Returns the section object that the collection will be added to"""
        sections = self.get_json_response('/library/sections')
        if not sections or 'Directory' not in sections:
            return None

        sections = sections['Directory']
        find = self.section_id
        if type(find) == int:
            for section in sections:
                if int(section['key']) == int(find):
                    if section['type'] not in ['movie', 'show']:
                        print(f'Ignoring selected library section {find}, as it\'s not a movie or show library.')
                        break
                    print(f'Found section {find}: "{section["title"]}"')
                    self.section_type = section["type"]
                    return section

            print(f'Provided library section {find} could not be found...\n')

        print('\nChoose a library to scan:\n')
        choices = {}
        for section in sections:
            if section['type'] not in ['movie', 'show']:
                continue
            print(f'[{section["key"]}] {section["title"]}')
            choices[int(section['key'])] = section
        print()

        choice = input('Enter the library number (-1 to cancel): ')
        while not choice.isnumeric() or int(choice) not in choices:
            if choice == '-1':
                return None
            choice = input('Invalid section, please try again (-1 to cancel): ')

        self.section_id = int(choice)
        self.section_type = choices[int(choice)]["type"]
        print(f'\nSelected "{choices[int(choice)]["title"]}"\n')
        return choices[int(choice)]



    def get_all_items(self):
        """Returns all the media items from the library"""

        lib_type = 1 if self.section_type == 'movie' else 4
        try:
            data = self.get_json_response(f'/library/sections/{self.section_id}/all', { 'type' : f'{lib_type}' })
            return data['Metadata']
        except Exception as e:
            print('Unable to get library data, cannot continue')
            return None


    def process_item_group(self, group):
        key = group[0]['key']
        if len(group) > 1:
            key += ',' + ','.join([item['ratingKey'] for item in group[1:]])

        metadataItems = self.get_metadata(key)
        if not metadataItems:
            print('Error getting metadata for this group, ignoring')
        
        metadataItems = metadataItems['Metadata']
        for metadata in metadataItems:
            if not metadata:
                continue
            metadata_id = metadata['ratingKey']

            media_title = metadata['title']
            if self.section_type == 'show':
                media_title = f'{metadata["grandparentTitle"]} - S{str(metadata["parentIndex"]).rjust(2, "0")}E{str(metadata["index"]).rjust(2, "0")} - {media_title}'
            extras = metadata['Extras']
            self.mediaItems[media_title] = { 'collections' : [], 'id' : metadata_id, 'has_extras' : False }
            if not extras or extras['size'] == 0:
                continue

            for extra in extras['Metadata']:
                if extra['guid'] and extra['guid'].startswith('file:///'):
                    self.mediaItems[media_title]['has_extras'] = True
                    break

            self.mediaItems[media_title]['collections'] = [collection['tag'] for collection in metadata['Collection']] if 'Collection' in metadata else []


    def get_metadata(self, loc):
        """Retrieves the metadata for the item specified by loc"""

        try:
            metadata = self.get_json_response(loc, { 'includeExtras' : '1' })
        except:
            return False

        return metadata


    def post_process(self):
        """Processes the results of the scan

        Prints out all items with extras and adds the media to the extras collection if it's not already in it
        """

        lib_type = 'Movie(s)' if self.section_type == 'movie' else 'Episode(s)'
        extras_count = len([item for item in self.mediaItems if self.mediaItems[item]['has_extras']])
        print(f'\nFound {extras_count} {lib_type.lower()} with extras')
        added = []
        removed = []
        print()
        print(f'{lib_type} already in "{self.collection_name}":')
        print(f'===========================================')
        for item in self.mediaItems.keys():
            has_extras = self.mediaItems[item]['has_extras']
            collections = self.mediaItems[item]['collections']
            if self.collection_name in collections:
                if has_extras:
                    print(item)
                else:
                    if not self.no_delete:
                        collections = [collection for collection in collections if collection != self.collection_name]
                        self.set_collections(self.mediaItems[item]['id'], collections)
                    removed.append(item)
            elif has_extras:
                collections.append(self.collection_name)
                self.set_collections(self.mediaItems[item]['id'], collections)
                added.append(item)
        print(f'\nAdded {len(added)} new {lib_type.lower()} to collection:')
        print(f'===========================================')
        for item in added:
            print(item)

        if self.no_delete:
            print(f'\n{len(removed)} {lib_type.lower()} in collection without local extras:')
        else:
            print(f'\nRemoved {len(removed)} {lib_type.lower()} from collection:')
        print(f'===========================================')
        for item in removed:
            print(item)
        print()

    
    def set_collections(self, metadata_id, collections):
        """Sets an item's list of collections"""
        lib_type = 1 if self.section_type == 'movie' else 4
        url = f'{self.host}/library/sections/{self.section_id}/all?type={lib_type}&id={metadata_id}'
        for index in range(len(collections)):
            url += f'&collection%5B{index}%5D.tag.tag={urllib.parse.quote(collections[index])}'
        url += f'&X-Plex-Token={self.token}'
        options = requests.options(url)
        put = requests.put(url)
        put.close() # Are the close statements necessary?
        options.close()
        return


    def get_json_response(self, url, params={}):
        """Returns the JSON response from the given URL"""
        response = requests.get(self.url(url, params), headers={ 'Accept' : 'application/json' })
        if response.status_code != 200:
            data = None
        else:
            try:
                data = json.loads(response.content)['MediaContainer']
            except:
                print('ERROR: Unexpected JSON response:\n')
                print(response.content)
                print()
                data = None

        response.close()
        return data


    def url(self, base, params={}):
        """Builds and returns a url given a base and optional parameters. Parameter values are URL encoded"""
        real_url = f'{self.host}{base}'
        sep = '?'
        for key, value in params.items():
            real_url += f'{sep}{key}={parse.quote(value)}'
            sep = '&'

        return f'{real_url}{sep}X-Plex-Token={self.token}'


    def get_yes_no(self, prompt):
        """Prompt the user for a yes/no response, continuing to show the prompt until a value that starts with 'y' or 'n' is entered"""

        while True:
            response = input(f'{prompt} (y/n)? ')
            ch = response.lower()[0] if len(response) > 0 else 'x'
            if ch in ['y', 'n']:
                return ch == 'y'

    def adjacent_file(self, filename):
        """Returns the file path for a file that is in the same directory as this script"""

        return os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__))) + os.sep + filename

if __name__ == '__main__':
    runner = CommentaryCollection()
    runner.run()