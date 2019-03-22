#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NetData plugin for Nvidia GPU stats.

Requirements:
#	- Nvidia driver installed (this plugin uses the NVML library)
#	- nvidia-ml-py Python package (Python NVML wrapper) installed or copy the 'pynvml.py' file
#	  from the 'nvidia-ml-py' package (https://pypi.python.org/pypi/nvidia-ml-py/7.352.0) to
#	  '/usr/libexec/netdata/python.d/python_modules/'. For use with Python >=3.2 please se known bugs
#	  in the README file.


The MIT License (MIT)
Copyright (c) 2016 Jan Arnold

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

# @Title			: nv.chart
# @Project			:
# @Description		: NetData plugin for Nvidia GPU stats
# @Author			: Jan Arnold
# @Email			: jan.arnold (at) coraxx.net
# @Copyright		: Copyright (C) 2016  Jan Arnold
# @License			: MIT
# @Credits			:
# @Maintainer		: Jan Arnold
# @Date				: 2018/11/02
# @Version			: 0.6
# @Status			: stable
# @Usage			: automatically processed by netdata
# @Notes			: With default NetData installation put this file under
#					: /usr/libexec/netdata/python.d/
#					: and the config file under /etc/netdata/python.d/
# @Python_version	: 2.7.12 and 3.5.2
"""
# ======================================================================================================================
from bases.FrameworkServices.SimpleService import SimpleService
from subprocess import Popen, PIPE
from re import findall
try:
	import pynvml
except Exception as e:
	if isinstance(e, ImportError):
		self.error("Please install pynvml: pip install nvidia-ml-py")
	if isinstance(e, SyntaxError):
		self.error(
			"Please fix line 1671 in pynvml.py file from the nvidia-ml-py package. 'print c_count.value' must be",
			"'print(c_count.value)' to be compatible with Python >=3.2")
	raise e

## Plugin settings
update_every = 1
priority = 60000
retries = 10

ORDER = ['utilization', 'memoryutilization', 'memory', 'pcie', 'temperature', 'fan', 'power', 'ecc_errors']

CHARTS = {
	'memory': {
		'options': [None, 'Memory', 'MB', 'Memory', 'nv.memory', 'line'],
		'lines': [
			# generated dynamically
		]},
	'utilization': {
		'options': [None, 'Utilization', '%', 'Utilization', 'nv.utilization', 'line'],
		'lines': [
			# generated dynamically
		]},
	'memoryutilization': {
		'options': [None, 'Memory Utilization', '%', 'Memory Utilization', 'nv.memoryutilization', 'line'],
		'lines': [
			# generated dynamically
		]},
	'ecc_errors': {
		'options': [None, 'ECC errors', 'counts', 'ECC', 'nv.ecc', 'line'],
		'lines': [
			# generated dynamically
		]},
	'temperature': {
		'options': [None, 'GPU temperature', 'C', 'Temperature', 'nv.temperature', 'line'],
		'lines': [
			# generated dynamically
		]},
	'fan': {
		'options': [None, 'Fan speed', '%', 'Fans', 'nv.fan', 'line'],
		'lines': [
			# generated dynamically
		]},
	'pcie': {
		'options': [None, 'PCI Express Bandwidth Utilization', 'KiB/s', 'PCIe Utilization', 'nv.pcie', 'area'],
		'lines': [
			# generated dynamically
		]},
	'power': {
		'options': [None, 'Power Consumption', 'Watt', 'Power', 'nv.power', 'line'],
		'lines': [
			# generated dynamically
		]}
}


class Service(SimpleService):
	def __init__(self, configuration=None, name=None):
		SimpleService.__init__(self, configuration=configuration, name=name)

		# Chart
		self.order = ORDER
		self.definitions = CHARTS

	def check(self):
		## Check legacy mode
		try:
			self.legacy = self.configuration['legacy']
			if self.legacy == '': raise KeyError
			if self.legacy is True: self.info('Legacy mode set to True')
		except KeyError:
			self.legacy = False
			self.info("No legacy mode specified. Setting to 'False'")

		## Real memory clock is double (DDR double data rate ram). Set nvMemFactor = 2 in conf for 'real' memory clock
		try:
			self.nvMemFactor = int(self.configuration['nvMemFactor'])
			if self.nvMemFactor == '': raise KeyError
			self.info("'nvMemFactor' set to:",str(self.nvMemFactor))
		except Exception as e:
			if isinstance(e, KeyError):
				self.info("No 'nvMemFactor' configured. Setting to 1")
			else:
				self.error("nvMemFactor in config file is not an int. Setting 'nvMemFactor' to 1", str(e))
			self.nvMemFactor = 1

		## Initialize NVML
		try:
			pynvml.nvmlInit()
			self.info("Nvidia Driver Version:", str(pynvml.nvmlSystemGetDriverVersion()))
		except Exception as e:
			self.error("pynvml could not be initialized", str(e))
			pynvml.nvmlShutdown()
			return False

		## Get number of graphic cards
		try:
			self.unitCount = pynvml.nvmlUnitGetCount()
			self.deviceCount = pynvml.nvmlDeviceGetCount()
			self.debug("Unit count:", str(self.unitCount))
			self.debug("Device count", str(self.deviceCount))
		except Exception as e:
			self.error('Error getting number of Nvidia GPUs', str(e))
			pynvml.nvmlShutdown()
			return False

		## Get graphic card names
		data = self._get_data()
		name = ''
		for i in range(self.deviceCount):
			if i == 0:
				name = name + str(data["device_name_" + str(i)]) + " [{0}]".format(i)
			else:
				name = name + ' | ' + str(data["device_name_" + str(i)]) + " [{0}]".format(i)
		self.info('Graphics Card(s) found:', name)
		for chart in self.definitions:
			self.definitions[chart]['options'][1] = self.definitions[chart]['options'][1] + ' for ' + name
		## Dynamically add lines
		for i in range(self.deviceCount):
			gpuIdx = str(i)
			## Memory
			if data['device_mem_used_'+str(i)] is not None:
				self.definitions['memory']['lines'].append(['device_mem_used_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute', 1, 1024**2])
				# self.definitions['memory']['lines'].append(['device_mem_free_' + gpuIdx, 'free [{0}]'.format(i), 'absolute', 1, 1024**2])
			# self.definitions['memory']['lines'].append(['device_mem_total_' + gpuIdx, 'GPU:{0} total'.format(i), 'absolute', -1, 1024**2])

			## Utilization/usage
			if data['device_util_gpu_' + gpuIdx] is not None:
				self.definitions['utilization']['lines'].append(['device_util_gpu_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute'])
				self.definitions['memoryutilization']['lines'].append(['device_util_mem_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute'])

			## PCIE Bandwidth
			if data['device_util_pcie_tx_' + gpuIdx] is not None:
				self.definitions['pcie']['lines'].append(['device_util_pcie_tx_' + gpuIdx, 'tx [{0}]'.format(i), 'absolute', 1, 1])
				self.definitions['pcie']['lines'].append(['device_util_pcie_rx_' + gpuIdx, 'rx [{0}]'.format(i), 'absolute', 1, -1])

			## ECC errors
			if data['device_ecc_errors_L1_CACHE_VOLATILE_CORRECTED_' + gpuIdx] is not None:
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L1_CACHE_VOLATILE_CORRECTED_' + gpuIdx, 'L1 Cache Volatile Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L1_CACHE_VOLATILE_UNCORRECTED_' + gpuIdx, 'L1 Cache Volatile Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L1_CACHE_AGGREGATE_CORRECTED_' + gpuIdx, 'L1 Cache Aggregate Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L1_CACHE_AGGREGATE_UNCORRECTED_' + gpuIdx, 'L1 Cache Aggregate Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L2_CACHE_VOLATILE_CORRECTED_' + gpuIdx, 'L2 Cache Volatile Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L2_CACHE_VOLATILE_UNCORRECTED_' + gpuIdx, 'L2 Cache Volatile Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L2_CACHE_AGGREGATE_CORRECTED_' + gpuIdx, 'L2 Cache Aggregate Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_L2_CACHE_AGGREGATE_UNCORRECTED_' + gpuIdx, 'L2 Cache Aggregate Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_DEVICE_MEMORY_VOLATILE_CORRECTED_' + gpuIdx, 'Device Memory Volatile Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_DEVICE_MEMORY_VOLATILE_UNCORRECTED_' + gpuIdx, 'Device Memory Volatile Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_DEVICE_MEMORY_AGGREGATE_CORRECTED_' + gpuIdx, 'Device Memory Aggregate Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_DEVICE_MEMORY_AGGREGATE_UNCORRECTED_' + gpuIdx, 'Device Memory Aggregate Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_REGISTER_FILE_VOLATILE_CORRECTED_' + gpuIdx, 'Register File Volatile Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_REGISTER_FILE_VOLATILE_UNCORRECTED_' + gpuIdx, 'Register File Volatile Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_REGISTER_FILE_AGGREGATE_CORRECTED_' + gpuIdx, 'Register File Aggregate Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_REGISTER_FILE_AGGREGATE_UNCORRECTED_' + gpuIdx, 'Register File Aggregate Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_TEXTURE_MEMORY_VOLATILE_CORRECTED_' + gpuIdx, 'Texture Memory Volatile Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_TEXTURE_MEMORY_VOLATILE_UNCORRECTED_' + gpuIdx, 'Texture Memory Volatile Uncorrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_TEXTURE_MEMORY_AGGREGATE_CORRECTED_' + gpuIdx, 'Texture Memory Aggregate Corrected [{0}]'.format(i), 'absolute'])
				self.definitions['ecc_errors']['lines'].append(['device_ecc_errors_TEXTURE_MEMORY_AGGREGATE_UNCORRECTED_' + gpuIdx, 'Texture Memory Aggregate Uncorrected [{0}]'.format(i), 'absolute'])

			## Temperature
			if data['device_temp_' + gpuIdx] is not None:
				self.definitions['temperature']['lines'].append(['device_temp_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute'])

			## Fan
			if data['device_fanspeed_' + gpuIdx] is not None:
				self.definitions['fan']['lines'].append(['device_fanspeed_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute'])

			## Power
			if data['device_power_' + gpuIdx] is not None:
				self.definitions['power']['lines'].append(['device_power_' + gpuIdx, 'GPU:{0}'.format(i), 'absolute', 1, 1000])

		## Check if GPU Units are installed and add charts
		if self.unitCount:
			self.order.append('unit_fan')
			self.order.append('unit_psu')
			for i in range(self.unitCount):
				gpuIdx = str(i)
				if data['unit_temp_intake_' + gpuIdx] is not None:
					self.definitions['temperature']['lines'].append(['unit_temp_intake_' + gpuIdx, 'intake (unit {0})'.format(i), 'absolute'])
					self.definitions['temperature']['lines'].append(['unit_temp_exhaust_' + gpuIdx, 'exhaust (unit {0})'.format(i), 'absolute'])
					self.definitions['temperature']['lines'].append(['unit_temp_board_' + gpuIdx, 'board (unit {0})'.format(i), 'absolute'])
				if data['unit_fan_speed_' + gpuIdx] is not None:
					self.definitions['unit_fan'] = {
						'options': [None, 'Unit fan', 'rpm', 'Unit Fans', 'nv.unit', 'line'],
						'lines': [['unit_fan_speed_' + gpuIdx, 'Unit{0}'.format(i), 'absolute']]}
				if data['unit_psu_current_' + gpuIdx] is not None:
					self.definitions['unit_psu'] = {
						'options': [None, 'Unit PSU', 'mixed', 'Unit PSU', 'nv.unit', 'line'],
						'lines': [
							['unit_psu_current_' + gpuIdx, 'current (A) (unit {0})'.format(i), 'absolute'],
							['unit_psu_power_' + gpuIdx, 'power (W) (unit {0})'.format(i), 'absolute'],
							['unit_psu_voltage_' + gpuIdx, 'voltage (V) (unit {0})'.format(i), 'absolute']]}
		return True

	def _get_data(self):
		data = {}

		if self.deviceCount:
			for i in range(self.deviceCount):
				gpuIdx = str(i)
				handle = pynvml.nvmlDeviceGetHandleByIndex(i)
				name = pynvml.nvmlDeviceGetName(handle)
				brand = pynvml.nvmlDeviceGetBrand(handle)
				brands = ['Unknown', 'Quadro', 'Tesla', 'NVS', 'Grid', 'GeForce', 'Titan']

				### Get data ###
				## Memory usage
				try:
					mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
				except Exception as e:
					self.debug(str(e))
					mem = None

				## ECC errors
				try:
					_memError = {}
					_eccCounter = {}
					eccErrors = {}
					eccCounterType = ['VOLATILE_ECC', 'AGGREGATE_ECC']
					memErrorType = ['ERROR_TYPE_CORRECTED', 'ERROR_TYPE_UNCORRECTED']
					memoryLocationType = ['L1_CACHE', 'L2_CACHE', 'DEVICE_MEMORY', 'REGISTER_FILE', 'TEXTURE_MEMORY']
					for memoryLocation in range(5):
						for eccCounter in range(2):
							for memError in range(2):
								_memError[memErrorType[memError]] = pynvml.nvmlDeviceGetMemoryErrorCounter(handle,memError,eccCounter,memoryLocation)
							_eccCounter[eccCounterType[eccCounter]] = _memError
						eccErrors[memoryLocationType[memoryLocation]] = _eccCounter
				except Exception as e:
					self.debug(str(e))
					eccErrors = None

				## Temperature
				try:
					temp = pynvml.nvmlDeviceGetTemperature(handle,pynvml.NVML_TEMPERATURE_GPU)
				except Exception as e:
					self.debug(str(e))
					temp = None

				## Fan
				try:
					fanspeed = pynvml.nvmlDeviceGetFanSpeed(handle)
				except Exception as e:
					self.debug(str(e))
					fanspeed = None

				## Power
				try:
					power = pynvml.nvmlDeviceGetPowerUsage(handle)
				except Exception as e:
					self.debug(str(e))
					power = None

				## GPU and Memory Utilization
				try:
					util = pynvml.nvmlDeviceGetUtilizationRates(handle)
					gpu_util = util.gpu
					mem_util = util.memory
				except Exception as e:
					self.debug(str(e))
					gpu_util = None
					mem_util = None

				## PCI Express Bandwidth Utilization
				try: 
					pcie_tx = pynvml.nvmlDeviceGetPcieThroughput(handle, pynvml.NVML_PCIE_UTIL_TX_BYTES)
					pcie_rx = pynvml.nvmlDeviceGetPcieThroughput(handle, pynvml.NVML_PCIE_UTIL_RX_BYTES)
				except Exception as e:
					self.debug(str(e))
					pcie_tx = None
					pcie_rx = None

				### Packing data ###
				self.debug("Device", gpuIdx, ":", str(name))
				data["device_name_" + gpuIdx] = name

				self.debug("Brand:", str(brands[brand]))

				self.debug(str(name), "Temp      :", str(temp))
				data["device_temp_" + gpuIdx] = temp

				self.debug(str(name), "Mem total :", str(mem.total), 'bytes')
				data["device_mem_total_" + gpuIdx] = mem.total

				self.debug(str(name), "Mem used  :", str(mem.used), 'bytes')
				data["device_mem_used_" + gpuIdx] = mem.used

				self.debug(str(name), "Mem free  :", str(mem.free), 'bytes')
				data["device_mem_free_" + gpuIdx] = mem.free

				self.debug(str(name), "Utilization GPU  :", str(gpu_util), '%')
				data["device_util_gpu_" + gpuIdx] = gpu_util

				self.debug(str(name), "Utilization MEM  :", str(mem_util), '%')
				data["device_util_mem_" + gpuIdx] = mem_util

				self.debug(str(name), "Utilization PCIE TX  :", str(pcie_tx), '%')
				data["device_util_pcie_tx_" + gpuIdx] = pcie_tx

				self.debug(str(name), "Utilization PCIE RX  :", str(pcie_rx), '%')
				data["device_util_pcie_rx_" + gpuIdx] = pcie_rx

				self.debug(str(name), "Fan speed :", str(fanspeed), '%')
				data["device_fanspeed_" + gpuIdx] = fanspeed

				self.debug(str(name), "Power Usage :", str(power), 'Watt')
				data["device_power_" + gpuIdx] = power

				self.debug(str(name), "ECC errors:", str(eccErrors))
				if eccErrors is not None:
					data["device_ecc_errors_L1_CACHE_VOLATILE_CORRECTED_" + gpuIdx] = eccErrors["L1_CACHE"]["VOLATILE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_L1_CACHE_VOLATILE_UNCORRECTED_" + gpuIdx] = eccErrors["L1_CACHE"]["VOLATILE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_L1_CACHE_AGGREGATE_CORRECTED_" + gpuIdx] = eccErrors["L1_CACHE"]["AGGREGATE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_L1_CACHE_AGGREGATE_UNCORRECTED_" + gpuIdx] = eccErrors["L1_CACHE"]["AGGREGATE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_L2_CACHE_VOLATILE_CORRECTED_" + gpuIdx] = eccErrors["L2_CACHE"]["VOLATILE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_L2_CACHE_VOLATILE_UNCORRECTED_" + gpuIdx] = eccErrors["L2_CACHE"]["VOLATILE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_L2_CACHE_AGGREGATE_CORRECTED_" + gpuIdx] = eccErrors["L2_CACHE"]["AGGREGATE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_L2_CACHE_AGGREGATE_UNCORRECTED_" + gpuIdx] = eccErrors["L2_CACHE"]["AGGREGATE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_DEVICE_MEMORY_VOLATILE_CORRECTED_" + gpuIdx] = eccErrors["DEVICE_MEMORY"]["VOLATILE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_DEVICE_MEMORY_VOLATILE_UNCORRECTED_" + gpuIdx] = eccErrors["DEVICE_MEMORY"]["VOLATILE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_DEVICE_MEMORY_AGGREGATE_CORRECTED_" + gpuIdx] = eccErrors["DEVICE_MEMORY"]["AGGREGATE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_DEVICE_MEMORY_AGGREGATE_UNCORRECTED_" + gpuIdx] = eccErrors["DEVICE_MEMORY"]["AGGREGATE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_REGISTER_FILE_VOLATILE_CORRECTED_" + gpuIdx] = eccErrors["REGISTER_FILE"]["VOLATILE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_REGISTER_FILE_VOLATILE_UNCORRECTED_" + gpuIdx] = eccErrors["REGISTER_FILE"]["VOLATILE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_REGISTER_FILE_AGGREGATE_CORRECTED_" + gpuIdx] = eccErrors["REGISTER_FILE"]["AGGREGATE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_REGISTER_FILE_AGGREGATE_UNCORRECTED_" + gpuIdx] = eccErrors["REGISTER_FILE"]["AGGREGATE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_TEXTURE_MEMORY_VOLATILE_CORRECTED_" + gpuIdx] = eccErrors["TEXTURE_MEMORY"]["VOLATILE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_TEXTURE_MEMORY_VOLATILE_UNCORRECTED_" + gpuIdx] = eccErrors["TEXTURE_MEMORY"]["VOLATILE_ECC"]["ERROR_TYPE_UNCORRECTED"]
					data["device_ecc_errors_TEXTURE_MEMORY_AGGREGATE_CORRECTED_" + gpuIdx] = eccErrors["TEXTURE_MEMORY"]["AGGREGATE_ECC"]["ERROR_TYPE_CORRECTED"]
					data["device_ecc_errors_TEXTURE_MEMORY_AGGREGATE_UNCORRECTED_" + gpuIdx] = eccErrors["TEXTURE_MEMORY"]["AGGREGATE_ECC"]["ERROR_TYPE_UNCORRECTED"]
				else:
					data["device_ecc_errors_L1_CACHE_VOLATILE_CORRECTED_" + gpuIdx] = None

		## Get unit (S-class Nvidia cards) data
		if self.unitCount:
			for i in range(self.unitCount):
				gpuIdx = str(i)
				handle = pynvml.nvmlUnitGetHandleByIndex(i)

				try:
					fan = pynvml.nvmlUnitGetFanSpeedInfo(handle)
					fan_speed = fan.speed  # Fan speed (RPM)
					fan_state = fan.state  # Flag that indicates whether fan is working properly
				except Exception as e:
					self.debug(str(e))
					fan_speed = None
					fan_state = None

				try:
					psu = pynvml.nvmlUnitGetPsuInfo(handle)
					psu_current = psu.current  # PSU current (A)
					psu_power = psu.power  # PSU power draw (W)
					psu_state = psu.state  # The power supply state
					psu_voltage = psu.voltage  # PSU voltage (V)
				except Exception as e:
					self.debug(str(e))
					psu_current = None
					psu_power = None
					psu_state = None
					psu_voltage = None

				try:
					temp_intake = pynvml.nvmlUnitGetTemperature(handle,0)  # Temperature at intake in C
					temp_exhaust = pynvml.nvmlUnitGetTemperature(handle,1)  # Temperature at exhaust in C
					temp_board = pynvml.nvmlUnitGetTemperature(handle,2)  # Temperature on board in C
				except Exception as e:
					self.debug(str(e))
					temp_intake = None
					temp_exhaust = None
					temp_board = None

				self.debug('Unit fan speed:',str(fan_speed))
				data["unit_fan_speed_" + gpuIdx] = fan_speed

				self.debug('Unit fan state:',str(fan_state))
				data["unit_fan_state_" + gpuIdx] = fan_state

				self.debug('Unit PSU current:',str(psu_current))
				data["unit_psu_current_" + gpuIdx] = psu_current

				self.debug('Unit PSU power:', str(psu_power))
				data["unit_psu_power_" + gpuIdx] = psu_power

				self.debug('Unit PSU state:', str(psu_state))
				data["unit_psu_state_" + gpuIdx] = psu_state

				self.debug('Unit PSU voltage:', str(psu_voltage))
				data["unit_psu_voltage_" + gpuIdx] = psu_voltage

				self.debug('Unit temp intake:', str(temp_intake))
				data["unit_temp_intake_" + gpuIdx] = temp_intake

				self.debug('Unit temp exhaust:', str(temp_exhaust))
				data["unit_temp_exhaust_" + gpuIdx] = temp_exhaust

				self.debug('Unit temp board:', str(temp_board))
				data["unit_temp_board_" + gpuIdx] = temp_board

		## Get data via legacy mode
		if self.legacy:
			try:
				output, error = Popen(
					[
						"nvidia-settings",
						"-c", ":0",
						"-q", "GPUUtilization",
						"-q", "GPUCurrentClockFreqs",
						"-q", "GPUCoreTemp",
						"-q", "TotalDedicatedGPUMemory",
						"-q", "UsedDedicatedGPUMemory"
					],
					shell=False,
					stdout=PIPE,stderr=PIPE).communicate()
				output = repr(str(output))
				if len(output) < 800:
					raise Exception('Error in fetching data from nvidia-settings ' + output)
				self.debug(str(error), output)
			except Exception as e:
				self.error(str(e))
				self.error('Setting legacy mode to False')
				self.legacy = False
				return data
			for i in range(self.deviceCount):
				gpuIdx = str(i)
				if data["device_temp_" + gpuIdx] is None:
					coreTemp = findall('GPUCoreTemp.*?(gpu:\d*).*?\s(\d*)', output)[i][1]
					try:
						data["device_temp_" + gpuIdx] = int(coreTemp)
						self.debug('Using legacy temp for GPU {0}: {1}'.format(gpuIdx, coreTemp))
					except Exception as e:
						self.debug(str(e), "skipping device_temp_" + gpuIdx)
				if data["device_mem_used_" + gpuIdx] is None:
					memUsed = findall('UsedDedicatedGPUMemory.*?(gpu:\d*).*?\s(\d*)', output)[i][1]
					try:
						data["device_mem_used_" + gpuIdx] = int(memUsed)
						self.debug('Using legacy mem_used for GPU {0}: {1}'.format(gpuIdx, memUsed))
					except Exception as e:
						self.debug(str(e), "skipping device_mem_used_" + gpuIdx)
				if data["device_util_gpu_" + gpuIdx] is None:
					gpu_util = findall('(gpu:\d*).*?graphics=(\d*),.*?memory=(\d*)', output)[i][1]
					try:
						data["device_util_gpu_" + gpuIdx] = int(gpu_util)
						self.debug('Using legacy load_gpu for GPU {0}: {1}'.format(gpuIdx, gpu_util))
					except Exception as e:
						self.debug(str(e), "skipping device_util_gpu_" + gpuIdx)
				if data["device_util_mem_" + gpuIdx] is None:
					mem_util = findall('(gpu:\d*).*?graphics=(\d*),.*?memory=(\d*)', output)[i][2]
					try:
						data["device_util_mem_" + gpuIdx] = int(mem_util)
						self.debug('Using legacy load_mem for GPU {0}: {1}'.format(gpuIdx, mem_util))
					except Exception as e:
						self.debug(str(e), "skipping device_util_mem_" + gpuIdx)

		return data
