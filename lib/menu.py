import webbrowser

from gi.repository import Gtk, Gdk

from updatewindow import UpdateWindow, RetweetDialog, DeleteDialog, DeleteDirectMessageDialog
from preferences.filters import FilterDialog
from utils.settings import SETTINGS_VIEW
from utils.htmlentities import decode_url_entities

from plugins.twitter.output import DictObj
from plugins.twitter.tweetentry import TweetEntry

def ENTRY_POPUP_MENU():
    return [OpenMenuItem, OpenUserPageMenuItem, None, 
            ReplyMenuItem, RetweetMenuItem, FavMenuItem, 
            DeleteMenuItem, SearchConversationMenuItem]

def LINK_MENU_ITEMS():
    return {'reply': ReplyMenuItem,
            'retweet': RetweetMenuItem,
            'conversation': ConversationMenuItem,
            'fav': FavMenuItem,
            'unfav': UnFavMenuItem,
            'delete': DeleteMenuItem,
            'deletedm': DeleteDirectMessageMenuItem,
            'hashtag': TrackHashTagMenuItem,
            'user': ShowUserMenuItem,
            'moreconversation': SearchConversationMenuItem, }


class PopupMenuItem(Gtk.MenuItem):

    LABEL = ''

    def __init__(self, uri=None, api=None, scrolled_window=None):
        super(PopupMenuItem, self).__init__()

        self.uri = uri
        self.user, entry_id = uri.split('/')[3:6:2] if uri else [None]*2
        self.api = api
        self.parent = scrolled_window

        self.set_label(self.LABEL)
        self.set_use_underline(True)
        self.connect('activate', self.on_activate, entry_id)
        self.show()

    def _get_entry_from_dom(self, entry_id):
        dom = self.parent.webview.dom.get_element_by_id(entry_id)

        def _get_first_class(cls_name):
            return dom.get_elements_by_class_name(cls_name).item(0)

        img_url = _get_first_class('usericon').get_attribute('src')
        user_name = _get_first_class('username').get_attribute('data-user')
        full_name = _get_first_class('username').get_attribute('data-fullname')
        body = _get_first_class('body').get_inner_text().rstrip('\n')
        date_time = _get_first_class('datetime').get_inner_text()
        is_protected = bool(_get_first_class('icon-lock'))

        entry_dict = dict(
            date_time=date_time,
            id=entry_id.split('-')[0], # for replyed status
            image_uri=img_url,
            user_name=user_name,
            full_name=full_name,
            protected=is_protected,
            status_body=body
            )

        # print entry_dict
        return entry_dict

class OpenMenuItem(PopupMenuItem):

    LABEL = _('_Open this Tweet in browser')

    def on_activate(self, menuitem, entry_id):
        uri = self.uri.replace('gfeedline:', 'https:')
        webbrowser.open(uri)

class OpenUserPageMenuItem(PopupMenuItem):

    LABEL = _('_Open this _user page in browser')

    def on_activate(self, menuitem, entry_id):
        uri = 'https://twitter.com/%s' % self.user
        webbrowser.open(uri)

class ReplyMenuItem(PopupMenuItem):

    LABEL = _('_Reply')

    def on_activate(self, menuitem, entry_id):
        entry_dict = self._get_entry_from_dom(entry_id)
        account = self.api.account
        UpdateWindow(self.parent.liststore, 
                     entry_dict, account.source, account.user_name)

class RetweetMenuItem(PopupMenuItem):

    LABEL = _('Re_tweet')

    def __init__(self, uri=None, api=None, scrolled_window=None):
        super(RetweetMenuItem, self).__init__(uri, api, scrolled_window)
        self.account = api.account

        if uri:
            entry_id = self._get_entry_id(uri)
            dom = self.parent.webview.dom.get_element_by_id(entry_id)
            self.set_sensitive(self._is_enabled(dom))

    def _get_entry_id(self, uri):
        entry_id = uri.split('/')[-1]
        return entry_id

    def _is_enabled(self, dom):
        is_mine = dom.get_attribute('class').count('mine')
        is_protected = bool(dom.get_elements_by_class_name('protected').item(0))
        return not is_mine and not is_protected

    def on_activate(self, menuitem, entry_id):
        entry_dict = self._get_entry_from_dom(entry_id)
        dialog = RetweetDialog(self.account)

        dialog.run(entry_dict, self.parent.window)

class DeleteMenuItem(RetweetMenuItem):

    LABEL = _('_Delete')

    def _is_enabled(self, dom):
        is_mine = dom.get_attribute('class').count('mine')
        return is_mine

    def on_activate(self, menuitem, entry_id):
        entry_dict = self._get_entry_from_dom(entry_id)
        dialog = DeleteDialog(self.account)

        dialog.run(entry_dict, self.parent.window)

class DeleteDirectMessageMenuItem(DeleteMenuItem):

    def on_activate(self, menuitem, entry_id):
        entry_dict = self._get_entry_from_dom(entry_id)
        dialog = DeleteDirectMessageDialog(self.account)

        dialog.run(entry_dict, self.parent.window)

class FavMenuItem(RetweetMenuItem):

    LABEL = _('_Favorite')

    def _is_enabled(self, dom):
        return True

    def on_activate(self, menuitem, entry_id):
        twitter_account = self.api.account
        twitter_account.api.fav(entry_id)

class UnFavMenuItem(FavMenuItem):

    def on_activate(self, menuitem, entry_id):
        twitter_account = self.api.account
        twitter_account.api.unfav(entry_id)

class ConversationMenuItem(RetweetMenuItem):

    LABEL = _('Conversation')

    def _get_entry_id(self, uri):
        entry_id = uri.split('/')[-1]
        entry_id = entry_id.split('-')[0]
        return entry_id

    def _is_enabled(self, dom):
        in_reply_to = dom.get_attribute('data-inreplyto')
        self.in_reply_to_screen_name, self.in_reply_to_status_id = \
            in_reply_to.split('/') if in_reply_to else [None, None]

        return bool(in_reply_to)

    def on_activate(self, menuitem, entry_id):
        entry_id, inreplyto_id = entry_id.split('-')

        twitter_account = self.api.account
        cb = lambda data: self._cb(data, entry_id)
        twitter_account.api.show(self.in_reply_to_status_id, cb)

    def _cb(self, data, entry_id):
        data['id'] = "%s-%s" % (data['id'], entry_id)
        entry = DictObj(data)
        entry_dict = TweetEntry(entry).get_dict(self.api)
        text = self.parent.theme.template['status'].substitute(entry_dict)

        text = text.replace('\n', '')
        text = text.replace('\\', '\\\\')

        js = 'insertReplyed("%s", "%s")' % (text, entry_id)
        # print js
        self.parent.webview.execute_script(js)

class SearchConversationMenuItem(ConversationMenuItem):

    LABEL = _('View _Conversation')

    def _get_group_name(self):
        current_group_name = self.parent.webview.group_name

#        if not SETTINGS_VIEW.get_boolean('conversation-other-column'):
#            return current_group_name

        group_list = self.parent.liststore.get_group_list()
        page = self.parent.liststore.get_group_page(current_group_name)

        if page >= len(group_list) -1:
            page -= 1
        else:
            page += 1

        return group_list[page]

    def on_activate(self, menuitem, entry_id):
        group_name = self._get_group_name()
        username = self.api.account.user_name
        to_user = self.in_reply_to_screen_name
        argument = "%s/%s/%s" % (self.user, to_user, entry_id)

        source = {'source': 'Twitter',
                  'argument': argument,
                  'target': _('Related Results'),
                  'username': username,
                  'group': group_name,
                  'name': '@%s' % self.user,
                  'options': {}
                  }
        self.parent.liststore.append(source)

        notebook = self.parent.window.column.get_notebook_object(group_name)
        notebook.set_current_page(-1)

class TrackHashTagMenuItem(SearchConversationMenuItem):

    def _is_enabled(self, dom):
        return False

    def on_activate(self, menuitem, entry_id):
        group_name = self._get_group_name()
        username = self.api.account.user_name
        hashtag = decode_url_entities(entry_id)

        source = {'source': 'Twitter',
                  'argument': hashtag,
                  'target': _('Search'),
                  'username': username,
                  'group': group_name,
                  'name': hashtag,
                  'options': {}
                  }
        self.parent.liststore.append(source)

        notebook = self.parent.window.column.get_notebook_object(group_name)
        notebook.set_current_page(-1)

class ShowUserMenuItem(TrackHashTagMenuItem):

    def on_activate(self, menuitem, entry_id):
        group_name = self._get_group_name()
        username = self.api.account.user_name

        source = {'source': 'Twitter',
                  'argument': entry_id,
                  'target': _('User TimeLine'),
                  'username': username,
                  'group': group_name,
                  'name': "@"+entry_id,
                  'options': {'has_profile': True}
                  }
        self.parent.liststore.append(source)

        notebook = self.parent.window.column.get_notebook_object(group_name)
        notebook.set_current_page(-1)

class SearchMenuItem(PopupMenuItem):

    LABEL = _('_Search')

    def on_activate(self, menuitem, entry_id):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = clipboard.wait_for_text()

        uri = 'http://www.google.com/search?q=%s' % text
        webbrowser.open(uri)

class AddFilterMenuItem(PopupMenuItem):

    LABEL = _('_Add Filter')

    def on_activate(self, menuitem, entry_id):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        clipboard_text = clipboard.wait_for_text()

        filter_liststore = self.parent.liststore.filter_liststore

        dialog = FilterDialog(None)
        response_id, v = dialog.run(clipboard_text)

        if response_id == Gtk.ResponseType.OK:
            filter_liststore.append(v)
