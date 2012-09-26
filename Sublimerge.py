# Sublimerge by Borys Forytarz
# If you want to fork this code, feel free, but let me know :)
#
# https://github.com/borysf/Sublimerge

import sublime
import sublime_plugin
import re
import difflib

diffView = None


class SublimergeDiffer():
    def difference(self, text1, text2):
        last = None
        data = []

        for line in list(difflib.Differ().compare(text1.splitlines(1), text2.splitlines(1))):
            change = line[0]
            line = line[2:len(line)]

            part = None

            if change == '+':
                part = {'+': line, '-': ''}

            elif change == '-':
                part = {'-': line, '+': ''}

            elif change == ' ':
                part = line

            elif change == '?':
                continue

            if part != None:
                if isinstance(part, str) and isinstance(last, str):
                    data[len(data) - 1] += part
                elif isinstance(part, dict) and isinstance(last, dict):
                    if part['+'] != '':
                        data[len(data) - 1]['+'] += part['+']
                    if part['-'] != '':
                        data[len(data) - 1]['-'] += part['-']
                else:
                    data.append(part)

                last = part

        return data


class SublimergeView():
    left = None
    right = None
    window = None
    currentDiff = -1
    regions = []
    currentRegion = None
    stopScrollSync = False
    lastLeftPos = None
    lastRightPos = None
    scrollSyncRunning = False

    def __init__(self, window, left, right):
        self.window = window
        self.window.run_command('new_window')
        wnd = sublime.active_window()

        wnd.set_layout({
            "cols": [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
        })

        self.left = wnd.open_file(left.file_name())
        self.right = wnd.open_file(right.file_name())
        wnd.set_view_index(self.right, 1, 0)

        self.left.set_syntax_file(left.settings().get('syntax'))
        self.right.set_syntax_file(right.settings().get('syntax'))
        self.left.set_scratch(True)
        self.right.set_scratch(True)

    def loadDiff(self):
        text1 = self.left.substr(sublime.Region(0, self.left.size()))
        text2 = self.right.substr(sublime.Region(0, self.right.size()))

        self.insertDiffContents(SublimergeDiffer().difference(text1, text2))

        self.left.set_read_only(True)
        self.right.set_read_only(True)

    def insertDiffContents(self, diff):

        left = self.left
        right = self.right

        edit = left.begin_edit()
        left.erase(edit, sublime.Region(0, left.size()))
        left.end_edit(edit)

        edit = right.begin_edit()
        right.erase(edit, sublime.Region(0, right.size()))
        right.end_edit(edit)

        regions = []
        i = 0

        for part in diff:
            if not isinstance(part, dict):
                edit = left.begin_edit()
                left.insert(edit, left.size(), part)
                left.end_edit(edit)

                edit = right.begin_edit()
                right.insert(edit, right.size(), part)
                right.end_edit(edit)
            else:
                pair = {'regionLeft': None, 'regionRight': None, 'name': 'diff' + str(i), 'mergeLeft': '', 'mergeRight': '', 'merged': False}
                i += 1

                if len(part['+']) > 0:
                    edit = left.begin_edit()
                    start = left.size()

                    if len(part['-']) == 0:
                        left.insert(edit, start, re.sub("[^\s]", " ", part['+']))
                        length = len(part['+'])
                    else:
                        left.insert(edit, start, part['-'])
                        length = len(part['-'])

                    left.end_edit(edit)

                    pair['regionLeft'] = sublime.Region(start, start + length)

                    edit = right.begin_edit()
                    start = right.size()
                    right.insert(edit, start, part['+'])
                    right.end_edit(edit)

                    pair['regionRight'] = sublime.Region(start, start + len(part['+']))

                elif len(part['-']) > 0:
                    edit = right.begin_edit()
                    start = right.size()

                    if len(part['+']) == 0:
                        right.insert(edit, start, re.sub("[^\s]", " ", part['-']))
                        length = len(part['-'])
                    else:
                        right.insert(edit, start, part['+'])
                        length = len(part['+]'])

                    right.end_edit(edit)

                    pair['regionRight'] = sublime.Region(start, start + length)

                    edit = left.begin_edit()
                    start = left.size()
                    left.insert(edit, start, part['-'])
                    left.end_edit(edit)

                    pair['regionLeft'] = sublime.Region(start, start + len(part['-']))

                if pair['regionLeft'] != None and pair['regionRight'] != None:
                    pair['mergeLeft'] = part['+']
                    pair['mergeRight'] = part['-']
                    regions.append(pair)

        for pair in regions:
            self.createDiffRegion(pair)

        self.regions = regions
        self.selectDiff(0)

    def createDiffRegion(self, region):
        self.left.add_regions(region['name'], [region['regionLeft']], 'selection', 'dot', sublime.DRAW_OUTLINED)
        self.right.add_regions(region['name'], [region['regionRight']], 'selection', 'dot', sublime.DRAW_OUTLINED)

    def createSelectedRegion(self, region):
        self.left.add_regions(region['name'], [region['regionLeft']], 'selection', 'dot')
        self.right.add_regions(region['name'], [region['regionRight']], 'selection', 'dot')

    def selectDiff(self, diffIndex):
        if diffIndex >= 0 and diffIndex < len(self.regions):
            if self.currentRegion != None:
                if self.currentRegion['merged']:
                    self.createHiddenRegion(self.currentRegion)
                else:
                    self.createDiffRegion(self.currentRegion)

            self.currentRegion = self.regions[diffIndex]
            self.createSelectedRegion(self.currentRegion)

            self.currentDiff = diffIndex
            self.left.show(self.currentRegion['regionLeft'])
            self.right.show(self.currentRegion['regionRight'])

    def goUp(self):
        self.selectDiff(self.currentDiff - 1)

    def goDown(self):
        self.selectDiff(self.currentDiff + 1)

    def merge(self, direction):
        if (self.currentRegion != None):
            lenLeft = self.left.size()
            lenRight = self.right.size()
            if direction == '<<':
                source = self.right
                target = self.left
                sourceRegion = self.currentRegion['regionRight']
                targetRegion = self.currentRegion['regionLeft']
                contents = self.currentRegion['mergeLeft']

            elif direction == '>>':
                source = self.left
                target = self.right
                sourceRegion = self.currentRegion['regionLeft']
                targetRegion = self.currentRegion['regionRight']
                contents = self.currentRegion['mergeRight']

            target.set_read_only(False)
            source.set_read_only(False)

            edit = target.begin_edit()
            target.replace(edit, targetRegion, contents)
            target.end_edit(edit)

            edit = source.begin_edit()
            source.replace(edit, sourceRegion, contents)
            source.end_edit(edit)

            diffLenLeft = self.left.size() - lenLeft
            diffLenRight = self.right.size() - lenRight

            source.erase_regions(self.currentRegion['name'])
            target.erase_regions(self.currentRegion['name'])

            target.set_scratch(False)

            self.currentRegion = None
            del self.regions[self.currentDiff]

            for i in range(len(self.regions)):
                if i >= self.currentDiff:
                    self.regions[i]['regionLeft'] = sublime.Region(self.regions[i]['regionLeft'].begin() + diffLenLeft, self.regions[i]['regionLeft'].end() + diffLenLeft)
                    self.regions[i]['regionRight'] = sublime.Region(self.regions[i]['regionRight'].begin() + diffLenRight, self.regions[i]['regionRight'].end() + diffLenRight)

            target.set_read_only(True)
            source.set_read_only(True)

            self.selectDiff(self.currentDiff)

    def abandonUnmergedDiffs(self, side):
        if side == 'left':
            view = self.left
            regionKey = 'regionLeft'
            contentKey = 'mergeRight'
        elif side == 'right':
            view = self.right
            regionKey = 'regionRight'
            contentKey = 'mergeLeft'

        edit = view.begin_edit()
        for i in range(len(self.regions)):
            sizeBefore = view.size()
            view.replace(edit, self.regions[i][regionKey], self.regions[i][contentKey])
            sizeDiff = view.size() - sizeBefore

            if sizeDiff != 0:
                for j in range(i, len(self.regions)):
                    self.regions[j][regionKey] = sublime.Region(self.regions[j][regionKey].begin() + sizeDiff, self.regions[j][regionKey].end() + sizeDiff)
        view.end_edit(edit)

    def syncScroll(self, enable):
        if enable:
            self.stopScrollSync = False
            self.periodicScrollSync()
        else:
            self.stopScrollSync = True

    def periodicScrollSync(self):
        return
        # if not self.scrollSyncRunning:
        #     self.scrollSyncRunning = True
        #     leftPos = self.left.viewport_position()
        #     rightPos = self.right.viewport_position()

        #     if leftPos != self.lastLeftPos:
        #         self.lastLeftPos = leftPos
        #         self.lastRightPos = leftPos

        #         self.right.set_viewport_position(leftPos, True)
        #     elif rightPos != self.lastRightPos:
        #         self.lastRightPos = rightPos
        #         self.lastLeftPos = rightPos

        #         self.left.set_viewport_position(rightPos, True)

        # self.scrollSyncRunning = False

        # if not self.stopScrollSync and self.left.window() != None:
        #     sublime.set_timeout(self.periodicScrollSync, 0)


class SublimergeCommand(sublime_plugin.WindowCommand):
    viewsList = []
    diffIndex = 0

    def run(self):
        self.viewsList = []
        self.diffIndex = 0
        active = self.window.active_view()
        allViews = self.window.views()

        for view in allViews:
            if view.file_name() != active.file_name():
                self.viewsList.append(view.file_name())

        if self.saved(active):
            self.window.show_quick_panel(self.viewsList, self.onListSelect)

    def saved(self, view):
        if view.is_dirty():
            sublime.error_message('File `' + view.file_name() + '` must be saved in order to compare')
            return False

        return True

    def onListSelect(self, itemIndex):
        if itemIndex > -1:
            allViews = self.window.views()
            compareTo = None
            for view in allViews:
                if (view.file_name() == self.viewsList[itemIndex]):
                    compareTo = view
                    break

            if compareTo != None:
                global diffView

                if self.saved(compareTo):
                    diffView = SublimergeView(self.window, self.window.active_view(), compareTo)


class SublimergeGoUpCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goUp()


class SublimergeGoDownCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goDown()


class SublimergeMergeLeftCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.merge('<<')


class SublimergeMergeRightCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.merge('>>')


class SublimergeListener(sublime_plugin.EventListener):
    left = None
    right = None

    def on_load(self, view):
        global diffView

        if diffView != None:
            if view.id() == diffView.left.id():
                print "Left file: " + view.file_name()
                self.left = view

            elif view.id() == diffView.right.id():
                print "Right file: " + view.file_name()

                self.right = view

            if self.left != None and self.right != None:
                diffView.loadDiff()
                diffView.syncScroll(True)
                self.left = None
                self.right = None

    def on_pre_save(self, view):
        global diffView

        if (diffView):
            if view.id() == diffView.left.id():
                diffView.abandonUnmergedDiffs('left')

            elif view.id() == diffView.right.id():
                diffView.abandonUnmergedDiffs('right')

    def on_close(self, view):
        global diffView
        if diffView != None:
            if view.id() == diffView.left.id() or view.id() == diffView.right.id():
                diffView.syncScroll(False)
                diffView = None
