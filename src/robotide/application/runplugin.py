#  Copyright 2008-2009 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os
import subprocess
import tempfile
import wx

from robotide.pluginapi import Plugin, ActionInfo, SeparatorInfo
from robotide.editor.listeditor import ListEditor


class RunAnything(Plugin):

    def __init__(self, app):
        Plugin.__init__(self, app, default_settings={'configs': []})

    def enable(self):
        self.register_action(ActionInfo('Run', 'New Run Configuration',
                                        self.OnNewConfiguration))
        self.register_action(ActionInfo('Run', 'Manage Run Configurations',
                                        self.OnManageConfigurations))
        self.register_action(SeparatorInfo('Run'))
        self._configs = _RunConfigs(self.configs)
        for config in self._configs:
            self._add_config_to_menu(config)

    def OnNewConfiguration(self, event):
        dlg = _ConfigDialog()
        if dlg.ShowModal() == wx.ID_OK:
            config = self._configs.add(*dlg.get_value())
            self._add_config_to_menu(config)
            self.save_setting('configs', self._configs.data_to_save())
        dlg.Destroy()

    def OnManageConfigurations(self, event):
        dlg = _ManageConfigsDialog(self._configs)
        dlg.ShowModal()
        dlg.Destroy()

    def _add_config_to_menu(self, config):
        def run(event):
            _Runner(_OutputWindow(self.notebook, config.name), config).run()
        info = ActionInfo('Run', name='%d: %s' % (config.index, config.name),
                          doc=config.help, action=run) 
        self.register_action(info)


class _RunConfigs(object):

    def __init__(self, saved_data):
        self._configs = []
        for item in saved_data:
            self.add(item[0], item[1], item[2])

    def __iter__(self):
        return iter(self._configs)

    def add(self, name, command, doc):
        config = _RunConfig(name, command, doc, len(self._configs)+1)
        self._configs.append(config)
        return config

    def data_to_save(self):
        return [ (c.name, c.command, c.doc) for c in self._configs ]


class _RunConfig(object):
    help = property(lambda self: '%s (%s)' % (self.doc, self.command))

    def __init__(self, name, command, doc, index):
        self.name = name
        self.command = command
        self.doc = doc
        self.index = index

    def run(self, output):
        # TODO: check subprocess usage in Windows
        self._process = subprocess.Popen(self.command, stdout=output,
                                         stderr=subprocess.STDOUT, shell=True)

    def finished(self):
        return self._process.poll() is not None


class _ConfigDialog(wx.Dialog):

    def __init__(self):
        wx.Dialog.__init__(self, wx.GetTopLevelWindows()[0],
                           title='New Run Configuration')
        self.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self._editors = []
        for label in ['Name', 'Command', 'Documentation']:
            self.Sizer.Add(self._get_entry_field(label))
        line = wx.StaticLine(self, size=(20,-1), style=wx.LI_HORIZONTAL)
        self.Sizer.Add(line, border=5,
                       flag=wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP)
        self.Sizer.Add(self.CreateStdDialogButtonSizer(wx.OK|wx.CANCEL),
                       flag=wx.ALIGN_CENTER|wx.ALL, border=5)
        self.Fit()

    def _get_entry_field(self, label):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label=label, size=(100, -1)))
        editor = wx.TextCtrl(self, size=(200,-1))
        sizer.Add(editor)
        self._editors.append(editor)
        return sizer

    def get_value(self):
        return [ e.GetValue() for e in self._editors ]


class _ManageConfigsDialog(wx.Dialog):

    def __init__(self, configs):
        wx.Dialog.__init__(self, wx.GetTopLevelWindows()[0],
                           title='Manage Run Configurations')
        self.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self._list = _ConfigListEditor(self, configs)
        self.Sizer.Add(self._list, flag=wx.GROW, proportion=1)
        line = wx.StaticLine(self, size=(20,-1), style=wx.LI_HORIZONTAL)
        self.Sizer.Add(line, border=5,
                       flag=wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP)
        buttons = self.CreateStdDialogButtonSizer(wx.OK|wx.CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnOk, buttons.GetAffirmativeButton())
        self.Sizer.Add(buttons, flag=wx.ALIGN_CENTER|wx.ALL, border=5)
        self.SetSize((750, 200))

    def OnOk(self, event):
        event.Skip()


class _ConfigListEditor(ListEditor):
    _buttons = ['New']

    def __init__(self, parent, configs):
        ListEditor.__init__(self, parent, None,
                            ['Name', 'Command', 'Documentation'], configs)
        self._list.col_locs = [0]
        loc = 0
        for n in range(self._list.GetColumnCount()):
            loc = loc + self._list.GetColumnWidth(n)
            self._list.col_locs.append(loc)

    def get_column_values(self, config):
        return config.name, config.command, config.doc

    def OnEdit(self, event):
        pass

    def OnNew(self, event):
        self._list.InsertStringItem(self._list.ItemCount, '')
        self._list.OpenEditor(0, self._list.ItemCount-1)

    def get_data(self):
        return [ [ self._list.GetItem(row, col).GetText() for col in range(3) ] 
                 for row in range(self._list.ItemCount) ]


class _Runner(wx.EvtHandler):

    def __init__(self, window, config):
        wx.EvtHandler.__init__(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer)
        self._timer = wx.Timer(self)
        self._window = window
        self._config = config

    def run(self):
        out_fd, path = tempfile.mkstemp()
        self._output = open(path)
        os.unlink(path)
        self._config.run(out_fd)
        self._timer.Start(500)

    def OnTimer(self, event):
        finished = self._config.finished()
        self._window.update_output(self._output.read(), finished)
        if finished:
            self._timer.Stop()


class _OutputWindow(wx.ScrolledWindow):

    def __init__(self, parent, name):
        wx.ScrolledWindow.__init__(self, parent)
        self.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self._output = wx.StaticText(self)
        self.Sizer.Add(self._output)
        self._name = name
        parent.add_tab(self, '%s (running)' % name)
        parent.show_tab(self)

    def update_output(self, output, finished=False):
        self._output.SetLabel(self._output.GetLabel() + output)
        if finished:
            self.Parent.rename_tab(self, '%s (finished)' % self._name)
