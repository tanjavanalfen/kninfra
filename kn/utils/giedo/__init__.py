import logging
import threading
import time

import grpc
import mirte  # github.com/bwesterb/mirte

from django.conf import settings

import kn.leden.entities as Es
import kn.utils.hans.hans_pb2_grpc as hans_pb2_grpc
from kn.utils.giedo._ldap import generate_ldap_changes
from kn.utils.giedo.db import update_db
from kn.utils.giedo.fotos import scan_fotos
from kn.utils.giedo.mailman import generate_mailman_changes
from kn.utils.giedo.postfix import (generate_postfix_map,
                                    generate_postfix_slm_map)
from kn.utils.giedo.siteagenda import update_site_agenda
from kn.utils.giedo.unix import generate_unix_map
from kn.utils.giedo.wiki import generate_wiki_changes
from kn.utils.giedo.wolk import generate_wolk_changes
from kn.utils.whim import WhimClient, WhimDaemon


class Giedo(WhimDaemon):

    def __init__(self):
        super(Giedo, self).__init__(settings.GIEDO_SOCKET)
        self.log = logging.getLogger('giedo')
        self.last_sync_ts = 0
        self.daan, self.cilia, self.moniek, self.hans = None, None, None, None
        try:
            self.daan = WhimClient(settings.DAAN_SOCKET)
        except Exception:
            self.log.exception("Couldn't connect to daan")
        try:
            self.cilia = WhimClient(settings.CILIA_SOCKET)
        except Exception:
            self.log.exception("Couldn't connect to cilia")
        try:
            self.moniek = WhimClient(settings.MONIEK_SOCKET)
        except Exception:
            self.log.exception("Couldn't connect to moniek")
        try:
            self.hans = hans_pb2_grpc.HansStub(
                grpc.insecure_channel('unix:' + settings.HANS_SOCKET))
        except Exception:
            self.log.exception("Couldn't connect to hans")
        self.mirte = mirte.get_a_manager()
        self.threadPool = self.mirte.get_a('threadPool')
        self.operation_lock = threading.Lock()
        self.ss_actions = (
            ('postfix', self.daan.send, self._gen_postfix),
            ('postfix-slm', self.daan.send, self._gen_postfix_slm),
            ('mailman', self.hans.ApplyChanges, self._gen_mailman),
            ('unix', self.cilia.send, self._gen_unix),
            ('wiki', self.daan.send, self._gen_wiki),
            ('ldap', self.daan.send, self._gen_ldap),
            ('wolk', self.cilia.send, self._gen_wolk))

    def pre_mainloop(self):
        super(Giedo, self).pre_mainloop()
        self.notify_systemd()

    def _gen_wolk(self):
        return {'type': 'wolk',
                'changes': generate_wolk_changes(self)}

    def _gen_ldap(self):
        return {'type': 'ldap',
                'changes': generate_ldap_changes(self)}

    def _gen_postfix_slm(self):
        return {'type': 'postfix-slm',
                'map': generate_postfix_slm_map(self)}

    def _gen_postfix(self):
        return {'type': 'postfix',
                'map': generate_postfix_map(self)}

    def _gen_mailman(self):
        return generate_mailman_changes(self.hans)

    def _gen_wiki(self):
        return {'type': 'wiki',
                'changes': generate_wiki_changes(self)}

    def _gen_unix(self):
        return {'type': 'unix',
                'map': generate_unix_map(self)}

    def sync(self):
        update_db_start = time.time()
        update_db(self)
        logging.info("update_db %s" % (time.time() - update_db_start))
        todo = [len(self.ss_actions)]
        todo_lock = threading.Lock()
        todo_event = threading.Event()

        def _sync_action(func, name, daemon, action):
            try:
                func(name, daemon, action)
            except Exception:
                logging.exception('uncaught exception in %s (daemon %s)' %
                                  (name, daemon))
            with todo_lock:
                todo[0] -= 1
                if todo[0] == 0:
                    todo_event.set()

        def _entry(name, send, action):
            start = time.time()
            msg = action()
            elapsed = time.time() - start
            logging.info("generate %s %.4f" % (name, elapsed))
            start = time.time()
            send(msg)
            elapsed = time.time() - start
            logging.info("send %s %.4f (%s to go)" %
                         (name, elapsed, todo[0] - 1))

        for action in self.ss_actions:
            self.threadPool.execute(_sync_action, _entry, *action)
        todo_event.wait()
        self.last_sync_ts = time.time()

    def handle(self, d):
        if d['type'] == 'sync':
            with self.operation_lock:
                return self.sync()
        elif d['type'] == 'setpass':
            with self.operation_lock:
                u = Es.by_name(d['user'])
                if u is None:
                    return {'error': 'no such user'}
                u = u.as_user()
                if not u.check_password(d['oldpass']):
                    return {'error': 'wrong old password'}
                u.set_password(d['newpass'])
                d2 = {'type': 'setpass',
                      'user': d['user'],
                      'pass': d['newpass']}
                self.daan.send(d2)
                self.cilia.send(d2)
                return {'success': True}
        elif d['type'] == 'ping':
            return {'pong': True}
        elif d['type'] == 'fotoadmin-scan-userdirs':
            return self.cilia.send(d)
        elif d['type'] == 'fotoadmin-move-fotos':
            with self.operation_lock:
                ret = self.daan.send(d)
                if 'success' not in ret:
                    return ret
                ret = scan_fotos()
                if 'success' not in ret:
                    return ret
                return self.cilia.send({
                    'type': 'fotoadmin-remove-moved-fotos',
                    'store': d['store'],
                    'user': d['user'],
                    'dir': d['dir']})
        elif d['type'] == 'fotoadmin-scan-fotos':
            with self.operation_lock:
                return scan_fotos()
        elif d['type'] == 'update-site-agenda':
            with self.operation_lock:
                return update_site_agenda(self)
        elif d['type'] in ['fotoadmin-create-event']:
            with self.operation_lock:
                return self.daan.send(d)
        elif d['type'] == 'last-synced?':
            return self.last_sync_ts
        elif d['type'] in ('fin-get-account',
                           'fin-get-debitors',
                           'fin-check-names',
                           'fin-get-gnucash-object',
                           'fin-get-years',
                           'fin-get-errors'):
            try:
                return self.moniek.send(d)
            except IOError as e:
                return {'error': 'IOError: ' + e.args[0]}
        else:
            logging.warn("Unknown command: %s" % d['type'])

# vim: et:sta:bs=2:sw=4:
