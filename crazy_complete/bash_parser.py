from collections import namedtuple

from . import utils
from . import shell
from .bash_utils import *

_PARSER_CODE = '''\
POSITIONALS=()
END_OF_OPTIONS=0
POSITIONAL_NUM=0

local command="${words[0]}" argi arg i char has_trailing_chars

for ((argi=1; argi < ${#words[@]} - 1; ++argi)); do
  arg="${words[argi]}"

  case "$arg" in
    --)
      END_OF_OPTIONS=1
      for ((++argi; argi < ${#words[@]}; ++argi)); do
        POSITIONALS[POSITIONAL_NUM++]="${words[argi]}"
      done
      break;;
    -)
      POSITIONALS[POSITIONAL_NUM++]="-";;
    -*)
%LONG_OPTION_CASES%
      for ((i=1; i < ${#arg}; ++i)); do
        char="${arg:$i:1}"
        has_trailing_chars=$( (( i + 1 < ${#arg} )) && echo true || echo false)
%SHORT_OPTION_CASES%
      done;;
    *)
      POSITIONALS[POSITIONAL_NUM++]="$arg"
%SUBCOMMAND_SWITCH_CODE%
      ;;
  esac
done

for ((; argi < ${#words[@]}; ++argi)); do
  arg="${words[$argi]}"

  case "$arg" in
    -) POSITIONALS[POSITIONAL_NUM++]="$arg";;
    -*);;
    *) POSITIONALS[POSITIONAL_NUM++]="$arg";;
  esac
done'''

def get_command(commandline):
    cmd = ' '.join(c.prog for c in commandline.get_parents(include_self=True))
    return cmd

def generate(commandline):
    commandlines = []
    commandline.visit_commandlines(lambda o: commandlines.append(o))
    commandlines = reversed(commandlines)

    long_option_cases = []
    short_option_cases = []
    subcommand_call_code = []

    for commandline in commandlines:
        option_cases = generate_option_cases(commandline)
        command = shell.escape(get_command(commandline))
        if commandline.inherit_options:
            command += '*'

        if option_cases.long_options:
            r =  'case "$command" in %s)\n' % command
            r += '  case "$arg" in\n'
            for case in option_cases.long_options:
                r += '%s\n' % utils.indent(case, 4)
            r += '  esac\n'
            r += 'esac\n'
            long_option_cases.append(r)

        if option_cases.short_options:
            r =  'case "$command" in %s)\n' % command
            r += '  case "$char" in\n'
            for case in option_cases.short_options:
                r += '%s\n' % utils.indent(case, 4)
            r += '  esac\n'
            r += 'esac\n'
            short_option_cases.append(r)

        if commandline.get_subcommands_option():
            r =  'if test $POSITIONAL_NUM -eq %d; then\n' % commandline.get_subcommands_option().get_positional_num()
            r += '  case "$arg" in\n'
            for subcommand in commandline.get_subcommands_option().subcommands:
                r += '    %s)\n' % '|'.join(utils.get_all_command_variations(subcommand))
                r += '      command+=" %s";;\n' % subcommand.prog
            r += '    *) command+=" $arg";;\n'
            r += '  esac\n'
            r += 'fi'
            subcommand_call_code.append(r)

    s = _PARSER_CODE

    if long_option_cases:
        s = s.replace('%LONG_OPTION_CASES%', utils.indent('\n'.join(long_option_cases), 6))
    else:
        s = s.replace('%LONG_OPTION_CASES%\n', '')

    if short_option_cases:
        s = s.replace('%SHORT_OPTION_CASES%', utils.indent('\n'.join(short_option_cases), 8))
    else:
        s = s.replace('%SHORT_OPTION_CASES%\n', '')

    if subcommand_call_code:
        s = s.replace('%SUBCOMMAND_SWITCH_CODE%', utils.indent('\n\n'.join(subcommand_call_code), 6))
    else:
        s = s.replace('%SUBCOMMAND_SWITCH_CODE%\n', '')

    return s

def generate_option_cases(commandline):
    OptionCases = namedtuple('OptionCases', ['long_options', 'short_options'])
    options = commandline.get_options()

    if commandline.abbreviate_options:
        abbreviations = get_OptionAbbreviationGenerator(options)
    else:
        abbreviations = utils.DummyAbbreviationGenerator()

    option_cases = OptionCases([], [])

    for option in options:
        long_options  = abbreviations.get_many_abbreviations(option.get_long_option_strings())
        long_options += abbreviations.get_many_abbreviations(option.get_old_option_strings())
        short_options = option.get_short_option_strings()

        have_variable  = make_option_variable_name(option, prefix='HAVE_')
        value_variable = make_option_variable_name(option, prefix='VALUE_')

        if long_options:
            if option.takes_args == '?':
                r  = '%s)\n'              % make_long_options_case_without_arg(long_options)
                r += '  %s=1;\n'          % have_variable
                r += '  continue;;\n'
                r += '%s)\n'              % make_long_options_case_with_arg(long_options)
                r += '  %s=1\n'           % have_variable
                r += '  %s="${arg#*=}"\n' % value_variable
                r += '  continue;;'
                option_cases.long_options.append(r)
            elif option.takes_args:
                r  = '%s)\n'                     % make_long_options_case_without_arg(long_options)
                r += '  %s=1\n'                  % have_variable
                r += '  %s="${words[++argi]}"\n' % value_variable
                r += '  continue;;\n'
                r += '%s)\n'                     % make_long_options_case_with_arg(long_options)
                r += '  %s=1\n'                  % have_variable
                r += '  %s="${arg#*=}"\n'        % value_variable
                r += '  continue;;'
                option_cases.long_options.append(r)
            else:
                r  = '%s)\n'    % make_long_options_case_without_arg(long_options)
                r += '  %s=1\n' % have_variable
                r += '  continue;;'
                option_cases.long_options.append(r)

        if short_options:
            if option.takes_args == '?':
                r  = '%s)\n'    % make_short_options_case(short_options)
                r += '  %s=1\n' % have_variable
                r += '  if $has_trailing_chars; then\n'
                r += '    %s="${arg:$((i + 1))}"\n' % value_variable
                r += '  fi\n'
                r += '  continue 2;;'
                option_cases.short_options.append(r)
            elif option.takes_args:
                r  = '%s)\n'    % make_short_options_case(short_options)
                r += '  %s=1\n' % have_variable
                r += '  if $has_trailing_chars\n'
                r += '  then %s="${arg:$((i + 1))}"\n' % value_variable
                r += '  else %s="${words[++argi]}"\n'  % value_variable
                r += '  fi\n'
                r += '  continue 2;;'
                option_cases.short_options.append(r)
            else:
                r  = '%s)\n'    % make_short_options_case(short_options)
                r += '  %s=1;;' % have_variable
                option_cases.short_options.append(r)

    return option_cases
