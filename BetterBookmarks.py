import sublime, sublime_plugin, os, collections, json, hashlib

# Add our BetterBookmarks cache folder if it doesn't exist
def plugin_loaded():
   directory = '{:s}/User/BetterBookmarks'.format(sublime.packages_path())
   if not os.path.exists(directory):
      os.makedirs(directory)

def Log(message):
   print('[BetterBookmarks] ' + message)
   #if Settings().get('verbose', False):
   #   print('[BetterBookmarks] ' + message)

def Settings():
    return sublime.load_settings('BetterBookmarks.sublime-settings')

def Variable(var, window=None):
   window = window if window else sublime.active_window()
   return sublime.expand_variables(var, window.extract_variables())

# Takes a region and converts it to a list taking into consideration if
#  the user wants us to care about the order of the selection.
def FixRegion(mark):
   if Settings().get("ignore_cursor", True):
      return [mark.begin(), mark.end()]
   return [mark.a, mark.b]

class BetterBookmarksCommand(sublime_plugin.TextCommand):
   def __init__(self, edit):
      sublime_plugin.TextCommand.__init__(self, edit)
      self.filename = Variable('${file_name}')
      self.layers = None
      self.on_layer_setting_change()
      self.layer = Settings().get('default_layer')
      while not self.layers[0] == self.layer:
         self.layers.rotate(1)
      Settings().add_on_change('layer_icons', self.on_layer_setting_change)

   def on_layer_setting_change(self):
      self.layers = collections.deque(Settings().get('layer_icons'))

   def _is_empty(self):
      for layer in self.layers:
         if self.view.get_regions(self._get_region_name(layer)):
            return False

      return True

   # Get the path to the cache file.
   def _get_cache_filename(self):
      h = hashlib.md5()
      h.update(self.view.file_name().encode())
      filename = str(h.hexdigest())
      # print("缓存文件名：" + filename)
      return '{:s}/User/BetterBookmarks/{:s}.bb_cache'.format(sublime.packages_path(), filename)

   def _get_region_name(self, layer=None):
      return 'better_bookmarks_{}'.format(layer if layer else self.layer)

   # Renders the current layers marks to the view
   def _render(self):
      marks = self.view.get_regions(self._get_region_name())
      icon = Settings().get('layer_icons')[self.layer]['icon']
      scope = Settings().get('layer_icons')[self.layer]['scope']

      self.view.add_regions('better_bookmarks', marks, scope, icon, sublime.PERSISTENT | sublime.HIDDEN)

   # Internal function for adding a list of marks to the existing ones.
   #  Any marks that exist in both lists will be removed as this case is when the user is 
   #     attempting to remove a mark.
   def _add_marks(self, newMarks, layer=None):
      region = self._get_region_name(layer)
      marks = self.view.get_regions(region)
      for mark in newMarks:
         if mark in marks:
            marks.remove(mark)
         else:
            marks.append(mark)

      # print("marks 长度：" + str(len(marks)))
      self.view.add_regions(region, marks, '', '', 0)

      if layer == self.layer:
         self._render()

   def _show_marks(self):
      layer = self.layer
      region = self._get_region_name(layer)
      marks = self.view.get_regions(region)

      if len(marks) == 0:
         Log("marks is empty")
         return

      # 获取书签内容
      text_msg = []
      for mark in marks:
         text = self.view.substr(mark)
         if len(text) == 0:
            text = 'text is empth, region=' + str(mark)

         text_msg.append(text)

      def on_done(index): # 选中索引从0开始
         if index != -1:
            Log(index)
            index_text = text_msg[index]
            Log("选中:" + index_text )
            self.view.run_command('{}_bookmark'.format("prev"), {'name': 'better_bookmarks'})
         else:
            Log("取消选择")

      # 弹出选项框，传入字符串数组和回调函数
      sublime.active_window().show_quick_panel(text_msg, on_done)

   # Changes the layer to the given one and updates any and all of the status indicators.
   def _change_to_layer(self, layer):
      self.layer = layer
      status_name = 'bb_layer_status'

      status = Settings().get('layer_status_location', ['permanent'])

      if 'temporary' in status:
         sublime.status_message(self.layer)
      if 'permanent' in status:
         self.view.set_status(status_name, 'Bookmark Layer: {:s}'.format(self.layer))
      else:
         self.view.erase_status(status_name)
      if 'popup' in status:
         if self.view.is_popup_visible():
            self.view.update_popup(self.layer)
         else:
            self.view.show_popup(self.layer, 0, -1, 1000, 1000, None, None)

      self._render()

   def _save_marks(self):
      if not self._is_empty():
         Log('Saving BBFile for ' + self.filename)
         with open(self._get_cache_filename(), 'w') as fp:
            marks = {'filename': self.view.file_name(), 'bookmarks': {}}
            for layer in self.layers:
               marks['bookmarks'][layer] = [FixRegion(mark) for mark in self.view.get_regions(self._get_region_name(layer))]
            json.dump(marks, fp)

   def run(self, edit, **args):
      view = self.view
      subcommand = args['subcommand']

      if subcommand == 'mark_line':
         mode = Settings().get('marking_mode', 'selection')

         if mode == 'line':
            selection = view.lines(view.sel()[0])
         elif mode == 'selection':
            selection = view.sel()
         else:
            sublime.error_message('Invalid BetterBookmarks setting: \'{}\' is invalid for \'marking_mode\''.format(mode))

         line = args['line'] if 'line' in args else selection
         layer = args['layer'] if 'layer' in args else self.layer

         self._add_marks(line, layer)
      elif subcommand == 'cycle_mark':
         self.view.run_command('{}_bookmark'.format(args['direction']), {'name': 'better_bookmarks'})
      elif subcommand == 'show_marks':
         self._show_marks()
      elif subcommand == 'clear_marks':
         layer = args['layer'] if 'layer' in args else self.layer
         self.view.erase_regions('better_bookmarks')
         self.view.erase_regions(self._get_region_name(layer))
      elif subcommand == 'clear_all':
         self.view.erase_regions('better_bookmarks')
         for layer in self.layers:
            self.view.erase_regions(self._get_region_name(layer))
      elif subcommand == 'layer_swap':
         direction = args.get('direction')
         if direction == 'prev':
            self.layers.rotate(-1)
         elif direction == 'next':
            self.layers.rotate(1)
         else:
            sublime.error_message('Invalid layer swap direction.')

         self._change_to_layer(self.layers[0])
      elif subcommand == 'on_load':
         Log('Loading BBFile for ' + self.filename)
         try:
            with open(self._get_cache_filename(), 'r') as fp:
               data = json.load(fp)

               for name, marks in data['bookmarks'].items():
                  self._add_marks([sublime.Region(mark[0], mark[1]) for mark in marks], name)
         except Exception as e:
            Log("打开bookmark缓存文件异常：" + str(e))
            pass
         self._change_to_layer(Settings().get('default_layer'))
      elif subcommand == 'on_save':
         self._save_marks()
      elif subcommand == 'on_close':
         if Settings().get('cache_marks_on_close', False):
            print("cache_marks_on_close")
            self._save_marks()
         if Settings().get('cleanup_empty_cache_on_close', False) and self._is_empty():
            Log('Removing BBFile for ' + self.filename)
            try:
               os.remove(self._get_cache_filename())
            except FileNotFoundError as e:
               pass

# 定义一个全局变量，标记是否已经执行过on_load，没有执行过时，在文件活跃时重新调用一下on_load。
# 否则每次关闭ST再打开，并添加bookmark时，之前已添加的bookmark会全部丢失
did_run_on_load = 0

class BetterBookmarksEventListener(sublime_plugin.EventListener):
   def __init__(self):
      sublime_plugin.EventListener.__init__(self)

   def _contact(self, view, subcommand):
      view.run_command('better_bookmarks', {'subcommand': subcommand})

   def on_load_async(self, view):
      if Settings().get('uncache_marks_on_load'):
         self._contact(view, 'on_load')

   def on_activated_async(self, view):
      global did_run_on_load
      if did_run_on_load == 0:
         did_run_on_load = 1
         self._contact(view, 'on_load')

   def on_pre_save(self, view):
      if Settings().get('cache_marks_on_save'):
         self._contact(view, 'on_save')

   def on_close(self, view):
      if view.file_name():
         self._contact(view, 'on_close')
