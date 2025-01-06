from texttable import Texttable
from elasticsearch import Elasticsearch
import click
import json
import ConfigParser
import sys

filename = "/etc/.tes/sources.ini"
config = ConfigParser.ConfigParser()
config.read(filename)
try:
    host = config.get("Current","host")
    port = config.get("Current","port")
    auth = config.get("Current","auth")
except ConfigParser.NoSectionError as e:
    click.echo("Please configure atleast one elasticsearch host")
    sys.exit()

es =  Elasticsearch(hosts=[{'host': host, 'port': port, 'auth': auth}])




def draw_table(response):
    table = Texttable(max_width=150)
    table.add_row(response[0].keys())
    for item in response:
        table.add_row(item.values())
    return table.draw()

def draw_single_response_table(response):
    table = Texttable(max_width=140)
    table.add_row(response.keys())
    table.add_row(response.values())
    return table.draw()


def pretty_print(response):
    parsed = json.loads(json.dumps(response))
    click.echo(json.dumps(parsed, indent=4, sort_keys=True))
