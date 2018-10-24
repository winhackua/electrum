# -*- coding: utf-8 -*-
import asyncio
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import *

from electrum.util import inv_dict, bh2u, bfh
from electrum.i18n import _
from electrum.lnchan import Channel
from electrum.lnutil import LOCAL, REMOTE, ConnStringFormatError

from .util import MyTreeWidget, SortableTreeWidgetItem, WindowModalDialog, Buttons, OkButton, CancelButton
from .amountedit import BTCAmountEdit

class ChannelsList(MyTreeWidget):
    update_rows = QtCore.pyqtSignal()
    update_single_row = QtCore.pyqtSignal(Channel)

    def __init__(self, parent):
        MyTreeWidget.__init__(self, parent, self.create_menu, [_('Node ID'), _('Balance'), _('Remote'), _('Status')], 0)
        self.main_window = parent
        self.update_rows.connect(self.do_update_rows)
        self.update_single_row.connect(self.do_update_single_row)
        self.status = QLabel('')

    def format_fields(self, chan):
        labels = {}
        for subject in (REMOTE, LOCAL):
            available = chan.available_to_spend(subject)//1000
            label = self.parent.format_amount(available)
            bal_other = chan.balance(-subject)//1000
            available_other = chan.available_to_spend(-subject)//1000
            if bal_other != available_other:
                label += ' (+' + self.parent.format_amount(bal_other - available_other) + ')'
            labels[subject] = label
        return [
            bh2u(chan.node_id),
            labels[LOCAL],
            labels[REMOTE],
            chan.get_state()
        ]

    def create_menu(self, position):
        menu = QMenu()
        channel_id = self.currentItem().data(0, QtCore.Qt.UserRole)
        def close():
            netw = self.parent.network
            coro = self.parent.wallet.lnworker.close_channel(channel_id)
            try:
                _txid = netw.run_from_another_thread(coro)
            except Exception as e:
                self.main_window.show_error('Force-close failed:\n{}'.format(repr(e)))
        def force_close():
            netw = self.parent.network
            coro = self.parent.wallet.lnworker.force_close_channel(channel_id)
            try:
                _txid = netw.run_from_another_thread(coro)
            except Exception as e:
                self.main_window.show_error('Force-close failed:\n{}'.format(repr(e)))
        menu.addAction(_("Close channel"), close)
        menu.addAction(_("Force-close channel"), force_close)
        menu.exec_(self.viewport().mapToGlobal(position))

    @QtCore.pyqtSlot(Channel)
    def do_update_single_row(self, chan):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, QtCore.Qt.UserRole) == chan.channel_id:
                for i, v in enumerate(self.format_fields(chan)):
                    item.setData(i, QtCore.Qt.DisplayRole, v)

    @QtCore.pyqtSlot()
    def do_update_rows(self):
        self.clear()
        for chan in self.parent.wallet.lnworker.channels.values():
            item = SortableTreeWidgetItem(self.format_fields(chan))
            item.setData(0, QtCore.Qt.UserRole, chan.channel_id)
            self.insertTopLevelItem(0, item)

    def get_toolbar(self):
        b = QPushButton(_('Open Channel'))
        b.clicked.connect(self.new_channel_dialog)
        h = QHBoxLayout()
        h.addWidget(self.status)
        h.addStretch()
        h.addWidget(b)
        return h

    def update_status(self):
        channel_db = self.parent.network.channel_db
        num_nodes = len(channel_db.nodes)
        num_channels = len(channel_db)
        num_peers = len(self.parent.wallet.lnworker.peers)
        self.status.setText(_('{} peers, {} nodes, {} channels')
                            .format(num_peers, num_nodes, num_channels))

    def new_channel_dialog(self):
        lnworker = self.parent.wallet.lnworker
        d = WindowModalDialog(self.parent, _('Open Channel'))
        d.setMinimumWidth(700)
        vbox = QVBoxLayout(d)
        h = QGridLayout()
        local_nodeid = QLineEdit()
        local_nodeid.setText(bh2u(lnworker.node_keypair.pubkey))
        local_nodeid.setReadOnly(True)
        local_nodeid.setCursorPosition(0)
        remote_nodeid = QLineEdit()
        local_amt_inp = BTCAmountEdit(self.parent.get_decimal_point)
        local_amt_inp.setAmount(200000)
        push_amt_inp = BTCAmountEdit(self.parent.get_decimal_point)
        push_amt_inp.setAmount(0)
        h.addWidget(QLabel(_('Your Node ID')), 0, 0)
        h.addWidget(local_nodeid, 0, 1)
        h.addWidget(QLabel(_('Remote Node ID or connection string or invoice')), 1, 0)
        h.addWidget(remote_nodeid, 1, 1)
        h.addWidget(QLabel('Local amount'), 2, 0)
        h.addWidget(local_amt_inp, 2, 1)
        h.addWidget(QLabel('Push amount'), 3, 0)
        h.addWidget(push_amt_inp, 3, 1)
        vbox.addLayout(h)
        ok_button = OkButton(d)
        ok_button.setDefault(True)
        vbox.addLayout(Buttons(CancelButton(d), ok_button))
        suggestion = lnworker.suggest_peer() or b''
        remote_nodeid.setText(bh2u(suggestion))
        remote_nodeid.setCursorPosition(0)
        if not d.exec_():
            return
        local_amt = local_amt_inp.get_amount()
        push_amt = push_amt_inp.get_amount()
        connect_contents = str(remote_nodeid.text()).strip()
        self.parent.open_channel(connect_contents, local_amt, push_amt)
