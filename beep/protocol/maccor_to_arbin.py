# Copyright 2019 Toyota Research Institute. All rights reserved.
""" Parsing and conversion of maccor procedure files to arbin schedule files"""

import os
import re
from datetime import datetime
from beep import PROTOCOL_SCHEMA_DIR
from collections import OrderedDict
from monty.serialization import loadfn
from beep.protocol.arbin import Schedule

TEST_DIR = os.path.dirname(__file__)
TEST_FILE_DIR = os.path.join(TEST_DIR, "test_files")


class ProcedureToSchedule:
    """
    This class is a set of methods to convert from a maccor procedure file to
    an arbin schedule file. This is essentially a translation between two
    different system languages. Since the two systems are not equivalent,
    its not possible to perform an exact translation and some control methods
    cannot be supported.

    Args:
        procedure_dict_steps (OrderedDict): A dictionary containing each of
            the steps in the procedure

    """
    def __init__(self,
                 procedure_dict_steps
                 ):
        self.procedure_dict_steps = procedure_dict_steps

    def create_sdu(self, sdu_input_name, sdu_output_name):
        """
        Highest level function in the class. Takes a schedule file and replaces
        all of the steps with steps from the procedure file. Then writes the
        resulting schedule file to the output file.

        Args:
            sdu_input_name (str): the full path of the schedule file to use as a
                shell for the steps
            sdu_output_name (str): the full path of the schedule file to output

        """
        schedule = Schedule.from_file(sdu_input_name)
        # sdu_dict = Schedule.from_file(sdu_input_name)

        keys = list(schedule['Schedule'].keys())
        for key in keys:
            if 'Schedule' in key:
                del schedule['Schedule'][key]

        step_name_list, step_flow_ctrl = self.create_metadata()
        for step_index, step in enumerate(self.procedure_dict_steps):
            step_arbin = self.compile_to_arbin(self.procedure_dict_steps[step_index],
                                               step_index, step_name_list, step_flow_ctrl)
            key = '[Schedule_Step{}]'.format(step_index)
            schedule.set(['Schedule]']).update({key: step_arbin})
        schedule.to_file(sdu_output_name)

    def create_metadata(self):
        """
        Creates the necessary information so that flow control for the steps can be
        set up correctly.

        Returns:
            list: unique strings consisting of the step number and note
            dict: key value pairs for the loop control steps indicating
                which step the Loop step should GOTO when the end condition
                is not matched

        """
        step_name_list = []
        step_flow_ctrl = {}
        for indx, step in enumerate(self.procedure_dict_steps):
            step_name_list.append(str(indx + 1) + '-' + str(step['StepNote']))
            if 'Loop' in step['StepType']:
                loop_counter = int(re.search(r'\d+', step['StepType']).group())
                i = 1
                while (indx - i) > 1:
                    if self.procedure_dict_steps[abs(indx - i)]['StepType'] == '  Do {}  '.format(loop_counter):
                        do_index = abs(indx - i)
                        break
                    i = i + 1
                step_flow_ctrl.update({indx: step_name_list[do_index + 1]})
        return step_name_list, step_flow_ctrl

    def compile_to_arbin(self, step_abs, step_index, step_name_list, step_flow_ctrl,
                         current_range='Parallel-High'):
        """
        Takes a step from a maccor procedure file and converts it to an equivalent
        step for an arbin schedule file. Not all control modes are supported. Compatible
        modes are constant current, constant voltage, CCCV. Future support for power,
        resistance modes and complex modes such as formulas and waveforms is planned.

        Flow control for the steps is implemented by using the TC counters of the arbin
        schedule. Since only 4 counters are available, only 4 layer of Loops are possible.
        Do steps are converted to steps that reset the respective TC counter and the Loop
        steps are converted to steps that go to the step immediately after the Do step until
        the loop condition is met, while advancing the TC counter every time the Loop step is
        passed.

        Arbin control values decoded: Arbin is using a 20-bit value for control and masking
        off specific portions for each of the different actions (reset, increment, decrement)
        and using different bits for each of the different counters
        =====================================================================================================
        Step Number	Name	    CtrlValue	Ext1	Ext2    Reset Increment
        3	Loop (CI 0)	                0	   1	  0				    CI			                    00001
        7	First Loop (Reset)	        0	   2	  0				    T1			                    00010
        8	Loop (CI 1)	                0	   1	  0				    CI			                    00001
        16	Loop 2 ( HPPC)	            0	   2	  0				    T1			                    00010
        17	Loop (CI 2)	                0	   1	  0				    CI			                    00001
        21	Loop (CI 3)     	        0	   1	  0				    CI			                    00001
        25	Loop (CI 4)	                0	   1	  0				    CI			                    00001
        29	Loop (CI 5)	                0	   1	  0				    CI			                    00001
        35	Loop 3 (Cycling 30)	    65536	   13	  0			T1	    T2		00010 00000 00000 00000	01101
        36	Loop 4 (Cycling 100)	    0	   16	  0				    T4			                    10000
        37	Loop 5 (always true)	524288	   1	  0			T4	    CI		10000 00000 00000 00000	00001

        Args:
            step_abs (OrderedDict): A ordered dict of the maccor step to be converted
            step_index (int): The index of the step to be converted
            step_name_list (list): A list of the step labels to be used in the arbin
                schedule file
            step_flow_ctrl (dict): A dictionary of the loop steps as keys and the
                corresponding steps to go to after the
            current_range (str): The current range to use for the step, values can
            be 'Range1', 'Range2', 'Range3', and 'Parallel-High' depending on the
            cycler being used

        Returns:
            OrderedDict: The arbin step resulting from the conversion of the
                procedure step
        """

        ARBIN_SCHEMA = loadfn(os.path.join(PROTOCOL_SCHEMA_DIR, "arbin_schedule_schema.yaml"))
        blank_step = OrderedDict(ARBIN_SCHEMA['step_blank_body'])

        blank_step['m_szLabel'] = str(step_index + 1) + '-' + str(step_abs['StepNote'])
        blank_step['m_szCurrentRange'] = current_range

        # Current control mode with currents measured in Amps
        if step_abs['StepMode'] == 'Current ' and 'C' not in step_abs['StepValue']:
            if step_abs['Limits'] is not None:
                blank_step['m_szStepCtrlType'] = "CCCV"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue']
                    blank_step['m_szExtCtrlValue1'] = step_abs['Limits']['Voltage']
                    blank_step['m_szExtCtrlValue2'] = "0"
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = '-' + step_abs['StepValue']
                    blank_step['m_szExtCtrlValue1'] = step_abs['Limits']['Voltage']
                    blank_step['m_szExtCtrlValue2'] = "0"
            elif step_abs['Limits'] is None:
                blank_step['m_szStepCtrlType'] = "Current(A)"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue']
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = '-' + step_abs['StepValue']
            else:
                raise ValueError("Unable to set m_szStepCtrlType for current")

        # Current control mode currents measured in C-rate
        elif step_abs['StepMode'] == 'Current ' and 'C' in step_abs['StepValue']:
            if step_abs['Limits'] is not None:
                blank_step['m_szStepCtrlType'] = "CCCV"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue'].replace('C', '')
                    blank_step['m_szExtCtrlValue1'] = step_abs['Limits']['Voltage']
                    blank_step['m_szExtCtrlValue2'] = "0"
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = '-' + step_abs['StepValue'].replace('C', '')
            elif step_abs['Limits'] is None:
                blank_step['m_szStepCtrlType'] = "C-Rate"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue'].replace('C', '')
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = '-' + step_abs['StepValue'].replace('C', '')
            else:
                raise ValueError("Unable to set m_szStepCtrlType for current")

        # Voltage control mode and current limit measured in Amps
        elif step_abs['StepMode'] == 'Voltage ':
            if step_abs['Limits'] is not None and 'C' not in step_abs['Limits']['Current']:
                blank_step['m_szStepCtrlType'] = "CCCV"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['Limits']['Current']
                    blank_step['m_szExtCtrlValue1'] = step_abs['StepValue']
                    blank_step['m_szExtCtrlValue2'] = "0"
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = '-' + step_abs['Limits']['Current']
                    blank_step['m_szExtCtrlValue1'] = step_abs['StepValue']
                    blank_step['m_szExtCtrlValue2'] = "0"
            elif step_abs['Limits'] is None:
                blank_step['m_szStepCtrlType'] = "Voltage(V)"
                if step_abs['StepType'] == ' Charge ':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue']
                elif step_abs['StepType'] == 'Dischrge':
                    blank_step['m_szCtrlValue'] = step_abs['StepValue']
            else:
                raise ValueError("Unable to set m_szStepCtrlType for voltage")

        # Rest control mode
        elif step_abs['StepMode'] == '        ' and step_abs['StepType'] == '  Rest  ':
            if step_abs['Limits'] is None:
                blank_step['m_szStepCtrlType'] = "Rest"
            else:
                raise ValueError("Unable to set m_szStepCtrlType for voltage")

        # Flow control steps
        elif step_abs['StepMode'] == '        ' and step_abs['StepType'] in [' Loop 1 ', '  Do 1  ',
                                                                             ' Loop 2 ', '  Do 2  ',
                                                                             'AdvCycle', '  End   ']:
            if step_abs['StepType'] == 'AdvCycle':
                blank_step['m_szStepCtrlType'] = "Set Variable(s)"
                blank_step['m_szCtrlValue1'] = '0'
                blank_step['m_szExtCtrlValue1'] = '1'
                blank_step['m_szExtCtrlValue1'] = '0'
            elif 'Loop' in step_abs['StepType']:
                loop_counter = int(re.search(r'\d+', step_abs['StepType']).group())
                blank_step['m_szStepCtrlType'] = "Set Variable(s)"
                blank_step['m_szCtrlValue1'] = '0'
                blank_step['m_szExtCtrlValue1'] = str(2 ** loop_counter)
                blank_step['m_szExtCtrlValue1'] = '0'
                assert isinstance(step_abs['Ends']['EndEntry'], OrderedDict)
                loop_addendum = OrderedDict([('EndType', 'Loop Addendum'), ('Oper', '< '),
                                            ('Step', step_flow_ctrl[step_index].split('-')[0]),
                                             ('Value', step_abs['Ends']['EndEntry']['Value'])])
                step_abs['Ends']['EndEntry'] = [loop_addendum, step_abs['Ends']['EndEntry']]

            elif 'Do' in step_abs['StepType']:
                loop_counter = int(re.search(r'\d+', step_abs['StepType']).group())
                blank_step['m_szStepCtrlType'] = "Set Variable(s)"
                blank_step['m_szCtrlValue1'] = str(2 ** (loop_counter + 15))
                blank_step['m_szExtCtrlValue1'] = '0'
                blank_step['m_szExtCtrlValue1'] = '0'

            else:
                blank_step['m_szStepCtrlType'] = "Rest"
        else:
            raise ValueError("Unable to set StepMode for Flow control step")

        step_type = step_abs['StepType']

        # Ends
        if step_abs['Ends'] is not None:
            if isinstance(step_abs['Ends']['EndEntry'], OrderedDict):
                blank_step['m_uLimitNum'] = 1
                end = step_abs['Ends']['EndEntry']
                end_index = 0
                limit_key = "[Schedule_Step{}_Limit{}]".format(str(step_index), str(end_index))
                blank_step[limit_key] = OrderedDict(self.convert_end_to_limit(blank_step, end,
                                                                         step_index, step_name_list,
                                                                         step_type, step_flow_ctrl))
            elif isinstance(step_abs['Ends']['EndEntry'], list):
                blank_step['m_uLimitNum'] = len(step_abs['Ends']['EndEntry'])
                for end_index, end in enumerate(step_abs['Ends']['EndEntry']):
                    limit_key = "[Schedule_Step{}_Limit{}]".format(str(step_index), str(end_index))
                    blank_step[limit_key] = OrderedDict(self.convert_end_to_limit(blank_step, end,
                                                                             step_index, step_name_list,
                                                                             step_type, step_flow_ctrl))
        elif step_abs['Ends'] is None:
            blank_step['m_uLimitNum'] = 1
            end_index = 0
            limit_key = "[Schedule_Step{}_Limit{}]".format(str(step_index), str(end_index))
            blank_step[limit_key] = self.add_blank_limit()

        # Reports
        if step_abs['Reports'] is not None:
            if isinstance(step_abs['Reports']['ReportEntry'], OrderedDict):
                blank_step['m_uLimitNum'] = blank_step['m_uLimitNum'] + 1
                report = step_abs['Reports']['ReportEntry']
                report_index = 0
                limit_start = len(step_abs['Ends']['EndEntry'])
                limit_key = "[Schedule_Step{}_Limit{}]".format(str(step_index), str(report_index + limit_start))
                blank_step[limit_key] = OrderedDict(self.convert_report_to_logging_limit(report))
            elif isinstance(step_abs['Ends']['EndEntry'], list):
                blank_step['m_uLimitNum'] = blank_step['m_uLimitNum'] + len(step_abs['Ends']['EndEntry'])
                for report_index, report in enumerate(step_abs['Reports']['ReportEntry']):
                    limit_start = len(step_abs['Ends']['EndEntry'])
                    limit_key = "[Schedule_Step{}_Limit{}]".format(str(step_index), str(report_index + limit_start))
                    blank_step[limit_key] = OrderedDict(self.convert_report_to_logging_limit(report))

        blank_step['m_uLimitNum'] = str(blank_step['m_uLimitNum'])

        return blank_step

    def add_blank_limit(self):
        """
        Minor helper function to add a limit that immediately advances to the next step.

        Returns:
            dict: blank limit that advances to the next step immediately

        """
        ARBIN_SCHEMA = loadfn(os.path.join(PROTOCOL_SCHEMA_DIR, "arbin_schedule_schema.yaml"))
        limit = ARBIN_SCHEMA['step_blank_limit']
        limit['m_bStepLimit'] = "1"
        limit['m_bLogDataLimit'] = "0"
        limit['m_szGotoStep'] = "Next Step"
        limit['Equation0_szLeft'] = 'PV_CHAN_Step_Time'
        limit['Equation0_szCompareSign'] = '>'
        limit['Equation0_szRight'] = '0'
        return limit

    def convert_end_to_limit(self, blank_step, end, step_index, step_name_list, step_type, step_flow_ctrl):
        """
        Takes a normal ending condition from a maccor procedure and converts it to an equivalent
        limit for an arbin schedule file.

        Args:
            blank_step (OrderedDict): the arbin step that is being populated
            end (OrderedDict): the ending condition from the maccor to convert to arbin limit
            step_index (int): the index of the current step being converted
            step_name_list (list): the list of labels for the steps
            step_type (str): the type of step being converted so that the limit can be set
                appropriately
            step_flow_ctrl (dict): a dictionary of the loop steps (keys) and the goto
                steps (values)

        Returns:
            dict: the converted limit

        """
        ARBIN_SCHEMA = loadfn(os.path.join(PROTOCOL_SCHEMA_DIR, "arbin_schedule_schema.yaml"))
        limit = ARBIN_SCHEMA['step_blank_limit']
        limit['m_bStepLimit'] = "1"
        limit['m_bLogDataLimit'] = "1"

        if end['Step'] == str(int(step_index) + 2).zfill(3):
            limit['m_szGotoStep'] = 'Next Step'
        else:
            limit['m_szGotoStep'] = step_name_list[int(end['Step']) - 1]

        if end['EndType'] == 'Voltage ':
            limit['Equation0_szLeft'] = 'PV_CHAN_Voltage'
            limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '')
            limit['Equation0_szRight'] = end['Value']
        elif end['EndType'] == 'Current ' and blank_step['m_szStepCtrlType'] == "CCCV":
            limit['Equation0_szLeft'] = 'PV_CHAN_CV_Stage_Current'
            if step_type == ' Charge ':
                limit['Equation0_szRight'] = end['Value']
                limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '')
            elif step_type == 'Dischrge':
                limit['Equation0_szRight'] = '-' + end['Value']
                limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '').replace('<', '>')
            else:
                raise ValueError("Unable to convert end to limit for EndType:{} and Ctrl:{}".
                                 format(end['EndType'], blank_step['m_szStepCtrlType']))
        elif end['EndType'] == 'Current ' and blank_step['m_szStepCtrlType'] == "Voltage(V)":
            limit['Equation0_szLeft'] = 'PV_CHAN_Current'
            if step_type == ' Charge ':
                limit['Equation0_szRight'] = end['Value']
                limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '')
            elif step_type == 'Dischrge':
                limit['Equation0_szRight'] = '-' + end['Value']
                limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '').replace('<', '>')
            else:
                raise ValueError("Unable to convert end to limit for EndType:{} and Ctrl:{}".
                                 format(end['EndType'], blank_step['m_szStepCtrlType']))
        elif end['EndType'] == 'StepTime':
            limit['Equation0_szLeft'] = 'PV_CHAN_Step_Time'
            limit['Equation0_szCompareSign'] = '>'
            if '.' in end['Value']:
                nofrag, frag = end['Value'].split(".")
                frag = frag[:6]  # truncate to microseconds
                frag += (6 - len(frag)) * '0'  # add 0s
                elapsed = datetime.strptime(nofrag.replace('::', '00:00:0'),
                                            "%H:%M:%S").replace(microsecond=int(frag)) - \
                    datetime.strptime("00:00:00", "%H:%M:%S")
            else:
                elapsed = datetime.strptime(end['Value'].replace('::', '00:00:0'), "%H:%M:%S") - \
                    datetime.strptime("00:00:00", "%H:%M:%S")
            limit['Equation0_szRight'] = str(elapsed.total_seconds())
        elif end['EndType'] == 'Loop Cnt':
            loop_counter = int(re.search(r'\d+', step_type).group())
            limit['Equation0_szLeft'] = 'TC_Counter{}'.format(loop_counter)
            limit['Equation0_szCompareSign'] = end['Oper'].replace(' ', '')
            limit['Equation0_szRight'] = end['Value']

        elif end['EndType'] == 'Loop Addendum':
            loop_counter = int(re.search(r'\d+', step_type).group())
            limit['m_szGotoStep'] = step_flow_ctrl[step_index]
            limit['Equation0_szLeft'] = 'TC_Counter{}'.format(loop_counter)
            limit['Equation0_szCompareSign'] = '<'
            limit['Equation0_szRight'] = end['Value']

        else:
            raise ValueError("Unable to set end for type {}".format(end['EndType']))

        return limit

    def convert_report_to_logging_limit(self, report):
        """
        Takes the reporting conditions for the maccor step and converts them to the logging
        limits for the arbin step.

        Args:
            report (OrderedDict): the maccor condition for recording values

        Returns:
            dict: a logging limit that corresponds to the recording conditions for
                maccor report

        """
        ARBIN_SCHEMA = loadfn(os.path.join(PROTOCOL_SCHEMA_DIR, "arbin_schedule_schema.yaml"))
        limit = ARBIN_SCHEMA['step_blank_limit']
        limit['m_bStepLimit'] = "0"
        limit['m_bLogDataLimit'] = "1"
        limit['m_szGotoStep'] = 'Next Step'

        if report['ReportType'] == 'Voltage ':
            limit['Equation0_szLeft'] = 'DV_Voltage'
            limit['Equation0_szCompareSign'] = '>'
            limit['Equation0_szRight'] = report['Value']
        elif report['ReportType'] == ' Current ':
            limit['Equation0_szLeft'] = 'DV_Current'
            limit['Equation0_szRight'] = report['Value']
            limit['Equation0_szCompareSign'] = '>'
        elif report['ReportType'] == 'StepTime':
            limit['Equation0_szLeft'] = 'DV_Time'
            limit['Equation0_szCompareSign'] = '>'
            if '.' in report['Value']:
                nofrag, frag = report['Value'].split(".")
                frag = frag[:6]  # truncate to microseconds
                frag += (6 - len(frag)) * '0'  # add 0s
                elapsed = datetime.strptime(nofrag.replace('::', '00:00:0'),
                                            "%H:%M:%S").replace(microsecond=int(frag)) - \
                    datetime.strptime("00:00:00", "%H:%M:%S")
            else:
                elapsed = datetime.strptime(report['Value'].replace('::', '00:00:0'), "%H:%M:%S") - \
                    datetime.strptime("00:00:00", "%H:%M:%S")
            limit['Equation0_szRight'] = str(elapsed.total_seconds())

        return limit
