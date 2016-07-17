import re
from shutil import which
import subprocess
import threading

# Conservatively import as little as possible
from os.path import split as op_split
from webbrowser import open as wb_open

import sublime

from .mixins.output_panel import OutputPanelMixin
from .mixins.steps import StepsMixin


class BehaveCommand(OutputPanelMixin,
                    StepsMixin):

    """Base class for all Sublime commands that interact with behave"""

    def behave(self, *args, **kwargs):
        """Runs the behave command with `*args`, returns the output as a str.

        If print_stream=True, the output will be streamed in an output panel.
        """

        command = tuple(self.behave_command) + \
            tuple(arg for arg in args if arg)

        return self._launch_process(command,
                                    print_stream=kwargs.get('print_stream'))

    @property
    def behave_command(self):
        """The command used to launch behave.

        This can be set by modifying the behave_command setting. The setting
        should be a list. If not set, the plugin will try to find the behave
        executable in the environment.
        """
        settings = sublime.load_settings('BehaveToolkit.sublime-settings')
        behave = self.view.settings().get('behave_command',
                                          settings.get('behave_command', None))

        # If behave is configured
        if behave:
            return behave

        # If not, try to find it
        else:
            behave = which('behave')
            if not behave:
                sublime.status_message('behave could not be found. '
                                       'Is it installed?')
                raise Exception('behave could not be found. Is it installed?')
            return [behave]

    def _get_project_folder(self):
        """Gets the _last_ folder in the project to use as our cwd for the
        `_launch_process()` in `subprocess.Popen()`.

        We choose the last folder because it is more likely (IMO - MattDMo)
        that if the user already has a project open, they'll add the desired
        folder _last_ instead of first. YMMV.

        If there are no folder entries in the project, we'll just return the
        folder that houses the current file. Better than nothing I suppose...
        """

        proj_folders = self.view.window().folders()

        # If there's at least one entry in the list, return the last element
        if len(proj_folders) > 0:
            return proj_folders[-1]

        # Otherwise, show an informative dialog explaining the problem, open
        # the docs to the "Getting Started" page, and return the folder the
        # current file resides in. I have no idea if this is appropriate for
        # all the commands, but it's something.
        else:
            if sublime.ok_cancel_dialog("You either do not have a folder "
                                        "defined in your project, or you do "
                                        "not have a project open. Please open "
                                        "the folder that you would like to "
                                        "have Behave Toolkit working on. For "
                                        "now, we will use the folder of the "
                                        "current file.\n\nPlease hit OK to "
                                        "view the documentation on setting up "
                                        "your project."):
                wb_open("http://behavetoolkit.readthedocs.io/en/latest/gettingstarted.html")  # NOQA

            # Let's try to get the file's path
            try:
                file_path = self.view.file_name()

            # OK, view isn't saved. We'll give them a chance to save it.
            except AttributeError:
                sublime.ok_cancel_dialog("Please save the current view before "
                                         "continuing.")
                self.view.run_command("prompt_save_as")

            # Now, we split the file path and return the folder's name.
            finally:
                file_folder, file_name = op_split(file_path)
                return file_folder

    def _launch_process(self, command, print_stream=False):
        """Launches a process and returns its output as a string.

        If print_stream=True, it will also stream the output to an output
        panel.

        Raises an exception if behave is not configured properly.
        """

        startupinfo = None
        if sublime.platform() == 'windows':
            # Prevent Windows from opening a console when starting a process
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        process = subprocess.Popen(command,
                                   stdout=subprocess.PIPE,
                                   bufsize=1,
                                   universal_newlines=True,
                                   cwd=self._get_project_folder(),
                                   startupinfo=startupinfo)

        if print_stream:
            self.erase()
            streamer = StreamerThread(self.append, process.stdout)
            streamer.start()
            streamer.join()

        stdout, stderr = process.communicate()

        if re.match(r'ConfigError', stdout):
            raise Exception("An error occurred while launching behave.\n",
                            stdout)

        return stdout


class StreamerThread(threading.Thread):

    """Streams `stream` to the output panel."""

    def __init__(self, append, stream):
        super(StreamerThread, self).__init__()
        self.append = append
        self.stream = stream

    def run(self):
        for line in self.stream:
            self.append(line, end='')
