#!/usr/bin/python3
from collections import defaultdict
from xml.etree.ElementTree import fromstring, tostring
from xml.dom.minidom import parseString

import os
import re
import string
import json

PYTHON_DIR = os.path.dirname(__file__)


def xml_to_string(xml):
    xml_stripped = re.sub(r'>\s+<', '><', tostring(xml, 'unicode'))
    return parseString(xml_stripped).toprettyxml('  ')


class Template(string.Template):
    braceidpattern = '(?a:[_a-z\-][_a-z0-9\-]*)'


class Templates():
    def __init__(self):
        self.templates = {}

    def _remove_nodes_with_empty_attributes(self, element):
        for child in list(element):
            if any(value == '' for (attrib, value) in child.items()):
                element.remove(child)
            else:
                self._remove_nodes_with_empty_attributes(child)

    def _clean_xml(self, xml_str):
        xml = fromstring(xml_str)
        self._remove_nodes_with_empty_attributes(xml)
        return xml_to_string(xml)

    def _apply_template(self, template_name, variables):
        return Template(self.templates[template_name]
                ).substitute(defaultdict(str, variables))

    def apply_template(self, template_name, variables):
        is_xml = os.path.splitext(template_name)[1] == '.xml'
        result = self._apply_template(template_name, variables)
        return self._clean_xml(result) if is_xml else result

    def apply_xml_template(self, template_name, variables):
        return fromstring(self.apply_template(template_name, variables))

    def apply_json_template(self, template_name, variables):
        return json.loads(self.apply_template(template_name, variables))

    def load_template(self, path, filename):
        if filename not in self.templates:
            with open(f'{PYTHON_DIR}/{path}/{filename}',
                    'r', encoding='utf8') as template_file:
                self.templates[filename] = str(template_file.read())
