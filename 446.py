'''Base class for :mod:`argparse`-based interactive :mod:`cmd` sessions.

.. This software is released under an MIT/X11 open source license.
   Copyright 2014 Diffeo, Inc.

.. autoclass:: ArgParseCmd

'''
from __future__ import absolute_import
import argparse
from cmd import Cmd
import logging
import pdb
import shlex

class ArgParseCmd(Cmd):
    '''Base class for :mod:`argparse`-based interactive :mod:`cmd` sessions.

    This extends :class:`cmd.Cmd` to allow individual commands to
    configure an :class:`argparse.ArgumentParser` object.  If a command
    has a ``args_command()`` method in parallel with its ``do_command()``
    method, then:

    * ``args_command()`` is called with an :class:`~argparse.ArgumentParser`
      object as a parameter and may add arguments to it

    * ``do_command()`` takes a single argument, which is the parsed
      :class:`argparse.Namespace`

    For instance, a typical program could look like:

    .. code-block:: python

        class AProgram(ArgParseCmd):
            def __init__(self):
                ArgParseCmd.__init__(self)
                self.prompt = 'aprogram> '

            def args_command(self, parser):
                parser.add_argument('--frobnicate', action='store_true',
                    help='frobnicate the frabulator')
            def do_command(self, args):
                """do work with the frabulator"""
                if args.frobnicate:
                    self.stdout.write('frobnicating\\n')
                else:
                    self.stdout.write('not frobnicating\\n')

    Running ``help command`` or ``command --help`` will print the
    argparse-generated help, using the main function's docstring as
    the short description.  Input lines are split with the
    :class:`shlex` module, and so complex strings can be quoted.  If
    there is no ``args_...()`` function, the complete line is passed
    to the ``do_...()`` function, just as in the base :class:`cmd.Cmd`
    class.  If your command takes no parameters, providing an empty
    ``args_...()`` function is good practice.

    .. note:: In Python 2.7, :class:`cmd.Cmd` is an old-style class,
              and so :func:`super` and other new-style class features
              will not work with this class.

    In addition to ``help``, this provides a standard ``quit`` command,
    and rebinds end-of-file to be equivalent to ``quit``.

    For standalone programs, the external shell has generally already
    parsed the command line into a sequence of arguments.
    :meth:`add_arguments` adds required arguments to a
    :class:`argparse.ArgumentParser`, and :meth:`main` either runs the
    main loop or the requested command.

    .. code-block:: python

        parser = argparse.ArgumentParser()
        app = AProgram()
        app.add_arguments(parser)
        args = yakonfig.parse_args(parser, [yakonfig])
        app.main(args)

    .. automethod:: add_arguments
    .. automethod:: main
    .. automethod:: runcmd

    '''
    def add_arguments(self, parser):
        '''Add generic command-line arguments to a top-level argparse parser.

        After running this, the results from ``argparse.parse_args()``
        can be passed to :meth:`main`.

        '''
        commands = set(name[3:] for name in dir(self) if name.startswith('do_'))
        parser.add_argument('action', help='action to run', nargs='?',
                            choices=list(commands))
        parser.add_argument('arguments', help='arguments specific to ACTION',
                            nargs=argparse.REMAINDER)

    def main(self, args):
        '''Run a single command, or else the main shell loop.

        `args` should be the :class:`argparse.Namespace` object after
        being set up via :meth:`add_arguments`.

        '''
        if args.action:
            self.runcmd(args.action, args.arguments)
        else:
            self.cmdloop()

    def runcmd(self, cmd, args):
        '''Run a single command from pre-parsed arguments.

        This is intended to be run from :meth:`main` or somewhere else
        "at the top level" of the program.  It may raise
        :exc:`exceptions.SystemExit` if an argument such as ``--help``
        that normally causes execution to stop is encountered.

        '''
        dof = getattr(self, 'do_' + cmd, None)
        if dof is None:
            return self.default(' '.join([cmd] + args))
        argf = getattr(self, 'args_' + cmd, None)
        if argf is not None:
            parser = argparse.ArgumentParser(
                prog=cmd,
                description=getattr(dof, '__doc__', None))
            argf(parser)
            argl = parser.parse_args(args)
        else:
            argl = ' '.join(args)
        return dof(argl)

    def parseline(self, line):
        cmd, arg, line = Cmd.parseline(self, line)
        if cmd and cmd.strip() != '':
            dof = getattr(self, 'do_' + cmd, None)
            argf = getattr(self, 'args_' + cmd, None)
        else:
            argf = None
        if argf:
            parser = argparse.ArgumentParser(
                prog=cmd,
                description=getattr(dof, '__doc__', None))
            argf(parser)
            try:
                arg = parser.parse_args(shlex.split(arg))
            except SystemExit, e:
                return '', '', ''
        return cmd, arg, line

    def emptyline(self):
        pass

    def args_help(self, parser):
        parser.add_argument('command', nargs='?',
                            help='print help on this command')
    def do_help(self, args):
        '''print help on a command'''
        if args.command:
            f = getattr(self, 'help_' + args.command, None)
            if f:
                f()
                return

            f = getattr(self, 'do_' + args.command, None)
            if not f:
                msg = self.nohelp % (args.command,)
                self.stdout.write('{0}\n'.format(msg))
                return

            docstr = getattr(f, '__doc__', None)
            f = getattr(self, 'args_' + args.command, None)
            if f:
                parser = argparse.ArgumentParser(
                    prog=args.command,
                    description=docstr)
                f(parser)
                parser.print_help(file=self.stdout)
            else:
                if not docstr:
                    docstr = self.nohelp % (args.command,)
                self.stdout.write('{0}\n'.format(docstr))
        else:
            Cmd.do_help(self, '')

    def precmd(self, line):
        if line == 'EOF':
            return 'quit'
        return line

    def args_quit(self, parser):
        pass
    def do_quit(self, line):
        '''exit the program'''
        return True
