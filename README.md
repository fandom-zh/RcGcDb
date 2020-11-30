## Introduction
RcGcDb is a backend for handling Discord webhooks to which recent changes of MediaWiki wikis are being pushed to.    
Master branch shouldn't be used in production and there are no guarantees for it working fine. It's mostly being created to work with [Wiki-Bot](https://github.com/Markus-Rost/discord-wiki-bot/).
If you are looking for low-scale MW Discord webhook recent changes solution, look at [RcGcDw](https://gitlab.com/piotrex43/RcGcDw) which should be more production ready.    
MRs are still welcome. 

### Dependencies ###
* **Python 3.7+**
* beautifulsoup 4.6.0+
* aiohttp 3.6.2+
* lxml 4.2.1+
* nest-asyncio 1.4.0+

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