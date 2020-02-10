# Youtube Comment Scraper
This is a simple python script for scraping the comments of youtube. 

# Requirements
* python >= 3.0 (https://www.python.org/downloads/)
* python modules
  - lxml
  - cssselect
  - BeautifulSoup4
  - XlsxWriter
```
  python -m pip install lxml
  python -m pip install cssselect
  python -m pip install BeautifulSoup4
  python -m pip install XlsxWriter
```

# Usage

```
usage: comment_scraper.py [-h] [-u] [-p [0-9]+번] [-d] [-f comments]
                          https://www.youtube.com/watch?v=m6LNiUIN54U
                          
positional arguments:
  https://www.youtube.com/watch?v=m6LNiUIN54U
                        youtube url that you want to scrape comments.

optional arguments:
  -h, --help            show this help message and exit
  -u, --unique          scarape only the recent comment from the same user
  -p ([0-9]+번), --picks ([0-9]+번)
                        collect user's pick using this regular expression
  -d, --draw            draw lots using picks
  -f comments, --filename comments
                        file name of xlsx output file
```
```
# ex. Scraping the comments of youtube on a specific youtube URL.
#     comments.xlsx file will be generated.
> python comment_scraper.py https://www.youtube.com/watch?v=m6LNiUIN54U
```
```
# ex. If you do a subscriber event on your channel using comments, you can draw lots like this. 
#     winners.xlsx file has been generated.
> python comment_scraper.py https://www.youtube.com/watch?v=m6LNiUIN54U -u -p ([0-9]+번) -d
```
```
# ex. You can save subscriber's comments only using -s option. 
#     I recommend you to add youtube data api key using -k option.
#     ( You could find free api key at the following site;
#     https://developers.google.com/youtube/v3/docs/subscriptions/list?
#     apix=true&apix_params=%7B%22%20%20%20%20%20%20%20%20%20part%22%3A%22snippet%2CcontentDetails%20%20%20%20%20%20%20%20%20%22%2C%22channelId%22%3A%22UCAuUUnT6oDeKwE6v1NGQxug%22%7D )
> python comment_scraper.py https://www.youtube.com/watch?v=m6LNiUIN54U -u -p ([0-9]+번) -d -s -k AIzaSyAa8yy0GdcGPHdtD083HiGGx_S0vMPScDM
```
