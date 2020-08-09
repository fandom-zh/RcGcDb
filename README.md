## Introduction
RcGcDb is a backend for handling webhooks to which recent changes of MediaWiki wikis are being pushed to. 

### Dependencies ###
* **Python 3.6>**
* beautifulsoup 4.6.0>
* aiohttp 3.6.2>
* lxml 4.2.1>

#### Installation
```
$ git clone git@gitlab.com:chicken-riders/rcgcdb.git #clone repo
$ cd RcGcDb
$ python3 -m venv . #(optional, if you want to contain everything (you should!))
$ source bin/activate #(optional, see above)
$ pip3 install -r requirements.txt #install requirements (lxml may require additional distro packages, more on that here https://lxml.de/build.html)
$ nano settings.json.example #edit the configuration file
$ mv settings.json.example settings.json
$ python3 start.py
```