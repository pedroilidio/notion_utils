#!/bin/env python
import requests
import yaml
from pathlib import Path
from warnings import warn
from sys import argv
from notion_client import Client  # TODO: Use AsyncClient.
import bibtexparser

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR/"config.yml"
# Config file must contain "notion_token" and "references_page_id" keys, with
# values respectively being Notion's API integration token, and the page's ID
# that can be found in its URL.

# TODO: Automatically fetch or even better: create a database with these props.
PROPERTY_TYPES = {
   # 'Last Edited Time': 'last_edited_time',
   # 'Tags': 'multi_select',
   # 'Created': 'created_time',
   # 'Related task': 'relation',
   # 'Status': 'select',
   'Year': 'number',
   'DOI': 'rich_text',
   # 'PDF': 'files',
   'Publisher': 'rich_text',
   'Title': 'rich_text',
   'URL': 'url',
   'Journal': 'rich_text',
   'Month': 'rich_text',
   'Author': 'rich_text',
   'BibTeX': 'rich_text',
   'Name': 'title'
}


def doi2bibtex(doi):
    """Return a bibTeX string of metadata for a given DOI."""
    if not doi.startswith('http'):
        doi = "http://dx.doi.org/" + doi
    headers = {"accept": "application/x-bibtex"}  # Multiple lines.
    # One line version, but sometimes won't work.
    # headers = {"accept": "text/bibliography; style=bibtex"}  
    res = requests.get(doi, headers=headers)
    return res.text


def bibtex2properties(sbibtex):
    # FIXME: highly coupled to the database property scheme.
    """Convert bibtex to Notion's page properties object."""
    bibtex = bibtexparser.loads(sbibtex)
    d = {k.capitalize():v for k,v in bibtex.get_entry_list()[0].items()}

    # Conform to property names in the database.
    # NOTE: lowercase in Notion?
    d['URL'] = d.pop('Url')
    d['DOI'] = d.pop('Doi')
    d['Name'] = d.pop('Id').replace('_', ' ')
    d['BibTeX'] = bibtexparser.bwriter.to_bibtex(bibtex)
    d['Year'] = int(d['Year'])

    props = {}
    for k, v in d.items():
        prop_type = PROPERTY_TYPES.get(k, None)
        if not prop_type:
            continue
        if prop_type in ('rich_text', 'title'):
            props[k] = {prop_type: [{'type':'text', 'text':{'content':v}}]}
        else:
            props[k] = {prop_type: v}

    return props


class ReferencesDatabase:
    def __init__(self, client, database_id):
        self.client = client
        self.database_id = database_id
        # TODO: self.property_types =

    def fetch_ref_properties(self, doi):
        # FIXME: automatically fetch property types.
        return bibtex2properties(doi2bibtex(doi))

    def add_reference(self, doi):
        properties = self.fetch_ref_properties(doi)
        print(f'Adding reference: {doi}')
        self.client.pages.create(
            parent={'type': 'database_id', 'database_id': self.database_id},
            properties=properties)

    def add_references(self, doilist):
        len_doilist = len(doilist)
        for i, doi in enumerate(doilist):
            print(f'({i+1}/{len_doilist}) ', end='')
            self.add_reference(doi)

    def fill_doi_only_ref(self, page_object):
        doi = page_object['properties']['URL']['url']
        page_id = page_object['id']
        print(f'Fulfilling DOI-only reference:\n\tID: {page_id}\n\tDOI: {doi}')
        properties = self.fetch_ref_properties(doi)
        self.client.pages.update(page_id, properties=properties)

    def fetch_doi_only_refs(self):
        res = self.client.databases.query(
            database_id=self.database_id,
            filter={'and':[
                {'property':'Name', 'title': {'is_empty': True}},
                {'property':'URL', 'url':{'is_not_empty':True}}
            ]})
        return res['results']

    def fullfil_doi_only(self):
        doi_only_refs = self.fetch_doi_only_refs()
        if not doi_only_refs:
            print('No DOI-only references found.')
            return
        total = len(doi_only_refs)
        for i, ref in enumerate(doi_only_refs):
            print(f'({i+1}/{total}) ', end='')
            self.fill_doi_only_ref(ref)


def main(doilist):
    with open(CONFIG_PATH) as config_file:
        config = yaml.safe_load(config_file)

    print('Authenticating...')
    notion = Client(auth=config['notion_token'])

    references_database = ReferencesDatabase(
        client=notion,
        database_id=config['references_page_id'],
    )

    print('Searching for DOI-only references...')
    references_database.fullfil_doi_only()
    if doilist:
        print('Adding new references...')
        references_database.add_references(doilist)
    print('Done.')


if __name__ == '__main__':
    main(argv[1:])
