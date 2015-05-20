# Copyright (c) 2015 SUSE LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import distutils.sysconfig
import sys
import os
import glob
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler

class Gatherer:
    def __init__(self):
        logfile = '/var/log/gatherer.log'
        self.log = logging.getLogger('')
        self.log.setLevel(logging.WARNING)
        formatFile = logging.Formatter("%(asctime)s %(name)s - %(levelname)s: %(message)s")
        formatStream = logging.Formatter("%(levelname)s: %(message)s")

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatStream)
        self.log.addHandler(ch)

        if not os.access(logfile, os.W_OK):
            logfile = '/tmp/gatherer.log'

        fh = RotatingFileHandler(logfile,
                                 maxBytes=(1048576*5),
                                 backupCount=5)
        fh.setFormatter(formatFile)
        self.log.addHandler(fh)

        self.options = None
        self.modules = {}

    def _parseOptions(self):
        """
        Supports the command-line arguments listed below.
        """
        parser = argparse.ArgumentParser(
            description='Process args for retrieving all the Virtual Machines')
        parser.add_argument('-i', '--infile', action='store',
                            help='json input file')
        parser.add_argument('-o', '--outfile', action='store',
                            help='to write the output to (json)')
        parser.add_argument('-v', '--verbose', action='count',
                            help='increase log output verbosity')
        parser.add_argument('-l', '--list-modules', action='store_true',
                            help="list modules with options")
        args = parser.parse_args()
        self.options = args

    def listModules(self):
        params = {}
        if len(self.modules) == 0:
            self._loadModules()
        for (modname, mod) in self.modules.items():
            params[modname] = mod.parameter()
            params[modname]['module'] = modname
        return params

    def run(self):
        if len(self.modules) == 0:
            self._loadModules()

        with open(self.options.infile, 'r') as f:
            mgmNodes = json.load(f)

        output = list()
        for node in mgmNodes:
            if not 'module' in node:
                self.log.error("Missing module definition in infile. Skipping")
                continue
            modname = node['module']
            if modname not in self.modules:
                self.log.error("Unsupported module '%s'. Skipping", modname)
                continue
            if not node['host']:
                self.log.error("Invalid 'host' entry. Skipping '%s'", node['name'])
                continue
            if not node['user'] or not node['pass']:
                self.log.error("Invalid 'user' or 'pass' entry. Skipping '%s'", node['name'])
                continue
            worker = self.modules[modname].worker(node)
            output.append(worker.run())
        if self.options.outfile:
            with open(self.options.outfile, 'w') as f:
                json.dump(output, f, sort_keys=True, indent=4, separators=(',', ': '))
        else:
            print json.dumps(output, sort_keys=True, indent=4, separators=(',', ': '))

    def main(self):
        self._parseOptions()
        if self.options.verbose == 1:
            self.log.setLevel(logging.INFO)
        if self.options.verbose >= 2:
            self.log.setLevel(logging.DEBUG)

        if self.options.list_modules:
            installed_modules = self.listModules()
            if self.options.outfile:
                with open(self.options.outfile, 'w') as f:
                    json.dump(installed_modules, f, sort_keys=True, indent=4, separators=(',', ': '))
            else:
                print json.dumps(installed_modules, sort_keys=True, indent=4, separators=(',', ': '))
            return

        if not self.options.infile:
            self.log.error("infile parameter required")
            return

        self.run()

    def _loadModules(self):
        plib = distutils.sysconfig.get_python_lib()
        if os.path.exists('./lib/gatherer/modules/__init__.py'):
            plib = './lib'
        mod_path="%s/gatherer/modules" % plib
        self.log.info("module path: %s", mod_path)
        filenames = glob.glob("%s/*.py" % mod_path)
        filenames = filenames + glob.glob("%s/*.pyc" % mod_path)
        filenames = filenames + glob.glob("%s/*.pyo" % mod_path)
        for fn in filenames:
            basename = os.path.basename(fn)
            if basename.startswith("__init__.py"):
                continue
            if basename[-3:] == ".py":
                modname = basename[:-3]
            elif basename[-4:] in [".pyc", ".pyo"]:
                modname = basename[:-4]

            try:
                self.log.debug("load %s", modname)
                mod = __import__('modules.%s' % (modname), globals(), locals(), [modname])
                self.log.debug("DIR: %s", dir(mod))
                if not hasattr(mod, "parameter"):
                    self.log.error("Module %s has not a paramater function", modname)
                    continue
                if not hasattr(mod, "worker"):
                    self.log.error("Module %s has not a worker function", modname)
                    continue
                self.modules[modname] = mod
            except ImportError, e:
                raise
