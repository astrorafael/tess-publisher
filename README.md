# tess-publisher

Software to publish TESS-W / TESS-W-4C readings when no WiFi connection is available.

This software is a gateway program to publish TESS photometer readings to the STARS4ALL MQTT photometer network when no WiFi connection is available for instance in required radielectric silent environments. ![description](images/yebes.jpg), 
(Yebes Observatoty, OAN, Spain)

or when the WiFi router is not connected to the Internet,

There are two methods to get readings from a TESS photometer:
* Via a USB-serial port
* Via a TCP connection

The first method requires serial-enabled TESS photometers, which is not done by default. Contact the STARS4ALL team before purchasing one. The second method is always available.

The photometer emits readings in JSON format that are captured by this program, then timestamped and sent to the MQTT broker.
Although the photometer emits these strings every 1-2 seconds, it is ***highly recommended*** to send to the broker with a rate of one reading per 60 seconds. This is set in the `config.toml` configuration file described below.

This program *can handle several photometers* at the same time (i.e one TESS-W and one TESS4C) by configuring them in the `config.toml` configuration file.

## Installation

This utility is published in PyPI, so it can be installed with your favourite Python package manager. This document uses [UV](https://docs.astral.sh/uv/), an extremely fast Python package manager. It is ***highly recommended*** to create a Python virtual environment. The example assumes Python 3.12.

### Virtual environment creation

```bash
~$ pwd
/home/rafa
 ~$ mkdir tess
 ~$ cd tess
 tess$ uv venv --python 3.12
Using CPython 3.12.3 interpreter at: /usr/bin/python3.12
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate
```

### Package installation

```bash
~$ pwd

 tess$ uv pip install tess-publisher
```

## Configuration

### Configure groups

If using the serial port method, it is necessary to add the user `rafa` to the `dialout` group in order to have permissions to open the serial port.

```bash
 tess$ sudo usermod -a -G dialout rafa
```
It is necessary to open a new login session to take effect. Verify it with the following command:


```bash
 tess$ groups rafa
```

### Create an `.env` environment file

Some configuration values are read at runtime via enviroment variables (mostly credentials). In your `/home/rafa/tess` directory, create a `.env` file with the following contents:

```bash
PATH=/home/pi/repos/tessdb-server/.venv/bin:/usr/local/bin:/usr/bin:/bin
PYTHONIOENCODING=utf-8
VIRTUAL_ENV=/home/pi/tess/.venv

# MQTT stuff
MQTT_TRANSPORT=tcp
MQTT_HOST=test.mosquitto.org
MQTT_PORT=1883
MQTT_USERNAME=""
MQTT_PASSWORD=""
MQTT_CLIENT_ID=""
MQTT_TOPIC=foo/bar

# Administration API
ADMIN_HTTP_LISTEN_ADDR=localhost
ADMIN_HTTP_PORT=8080
```

The following contents will publish readings on a public MQTT broker and is valid for testing purposes only, not for production. ***Contact the STARS4ALL team to get the proper values for the MQTT_XXXX variables***

### Create/Edit a `config.toml` file

The reast of configuration values are stored in a `config.toml` file


```toml
# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

#------------------------------------------------------------------------#
[http]

# HTTP management interface section

# Connection is made by env variables ADMIN_HTTP_LISTEN_ADDR, ADMIN_HTTP_PORT

# http task log level (debug, info, warn, error, critical)
log_level = "info"

#------------------------------------------------------------------------#
[mqtt]

# MQTT Client config

# The broker host, username, password and client_id
# are configured by environment variables
# MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID
# respectively

# Keepalive connection (in seconds)
# Not reloadable property
keepalive = 60


# namespace log level (debug, info, warn, error, critical)
# Reloadable property
log_level = "info"

# MQTT PDUs log level. 
# See all PDU exchanges with 'debug' level. Otherwise, leave it to 'info'
# Reloadable property
protocol_log_level = "info"

#------------------------------------------------------------------------#

[tess]

# namespace log level (debug, info, warn, error, critical)
# Reloadable property
log_level = "info"

# Serial to MQTT queue size
qsize = 1000

# Photometers config data
# Non reloadable data
[tess.stars111]
endpoint = "serial:/dev/ttyACM0:9600"
period = 60 # MQTT TX period in seconds. Recommended value: 60
log_level = "info"
model = "TESS-W"
mac_address = "AA:BB:CC:DD:EE:FF"
zp1 = 20.5
offset1 = 0 # Frequency offset (dark current frequency)
filter1 = "UVIR750"


[tess.stars478]
endpoint = "tcp:192.168.4.1:23"
period = 60 # MQTT TX period in seconds. Recommended value: 60
log_level = "debug"
model = "TESS4C"
mac_address = "FF:AA:BB:CC:DD:EE"
zp1 = 20.5
offset1 = 0 # Frequency offset (dark current frequency)
filter1 = "UVIR750"
zp2 = 20.5
offset2 = 0 # Frequency offset (dark current frequency)
filter2 = "UVIR650"
zp3 = 20.5
offset3 = 0 # Frequency offset (dark current frequency)
filter3 = "RGB-R"
zp4 = 20.5
offset4 = 0 # Frequency offset (dark current frequency)
filter4 = "RGB-B"
firmware = "Mar  4 2024"
```


You need to configure the photometer-specific data. Other values are good as is. In the case of a single channel TESS-W photometer, we have:
* `endpoint`. This is where we specify if reading by serial or TCP port. The endpoint string has three fields separated by `:`. The first one specifies the communication method, the second one is the serial device or IP address and the third one is the baud rate in case of serial port (9600 is fine) or the TCP port to open.
* `period`. Send a message every *period* seconds. Leave it at 60.
* `model` is either `TESS-W` or `TESS4C` strings.
* `mac_address`: See your photometer label in the cable to get this important value.
* `zp1`: Photometer's zero point as calibrated by STARS4ALL.
* `offset1`: frequency offset when completely dark. Leave it a t zero.
* `filter1`: string identifying a mounted filter. All TESS-W models use an UV/IR cut of filter that cuts IR at 750nm. Leave it at "UVIR750" anless your photometer was delivered with a custom filter.

In the case of a 4-channel TESS-W, the `zp1`, `filter1` and `offset1` values must also be configured to channels 2, 3 & 4. You must also specify a `firmware` value. All these values can be looked up by connecting the photometer when it is configured as an [Access Point](http://192.168.4.1/config)






### Testing


### Linux service and log rotation

For convenience, it is *highly recommended* to install this software as a Linux service and its logfile managed by logrotate.


