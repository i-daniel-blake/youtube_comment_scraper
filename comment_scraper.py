import requests
import json
import html.parser
import lxml.html
import lxml.cssselect
import lxml.etree
import urllib.parse
from bs4 import BeautifulSoup
import re
import random
import xlsxwriter
import argparse
import concurrent.futures
import datetime

class Candidate(object):
    """Candidate"""
    
    def __init__(self, id, name, picks, comment, emails=None):
        self.id = id        # youtube channel id
        self.name = name
        self.picks = picks  # has to be set
        self.comment = comment
        self.emails = emails

    def __str__(self):
        return ' Name: {0}\n Picks: {1}\n Emails: {2}\n Comment: {3}'.format( self.name, self.picks, self.emails, self.comment ) 

    def to_excel_row(self):
        YOUTUbE_URL = 'https://www.youtube.com'
        emails = ', '.join( self.emails )
        picks = ', '.join( self.picks )
        row = [ self.name, 
                emails, 
                self.comment, 
                YOUTUbE_URL + self.id,
                picks ]     
        return row

    @staticmethod
    def excel_headers():
        return [    
                    { 'name':'Name', 'width':20 }, 
                    { 'name':'Email', 'width':25 }, 
                    { 'name':'Comment', 'width':30, 'text wrap':False },
                    { 'name':'Channel Url', 'width':55} ,
                    { 'name':'Pick', 'width':10 } 
                ]
    
    @staticmethod
    def excel_headers_for_winner():
        headers = [ 
                    {'name':'Pick', 'width':10 }, 
                    {'name':'The number of candidates', 'width':10 },
                    {'name':'Candidates', 'width':25, 'text_wrap':True } 
                ]

        for header in Candidate.excel_headers():
            header['name'] = "Winner's " + header['name']
            headers.append( header )

        return headers


class CommentTokens(object):
    """CommentTokens"""

    def __init__(self, ctoken, itct, session_token, channel_id):
        self.ctoken = ctoken
        self.itct = itct
        self.session_token = session_token
        self.channel_id = channel_id

    def dump(self):
        print( '[SShampoo] CommentTokens - ctoken: {0}, itct: {1}, session_token: {2}, channel_id: {3}'.format( self.ctoken, self.itct, self.session_token, self.channel_id ) )


def get_initial_data_of_youtube( doc ):
    INIT_DAT_PREFIX         = 'window["ytInitialData"] ='
    SESSION_TOKEN_PREFIX    = '"XSRF_TOKEN":"'

    session_token = None
    initial_data = ''

    lines = doc.splitlines()
    for line in lines:
        line = line.strip()
        if session_token is None and line.find( SESSION_TOKEN_PREFIX ) > 0:
            start = line.find( SESSION_TOKEN_PREFIX ) + len( SESSION_TOKEN_PREFIX )
            end = line.find( '",', start )
            session_token = line[start:end]         

        if line.startswith( INIT_DAT_PREFIX ) :
            initial_data = line[ len(INIT_DAT_PREFIX) : -1 ]
            break

    return initial_data, session_token
    

def get_subscribed_channel_id( session, browse_url ):
    YOUTUBE_HOST_URL = 'https://www.youtube.com'

    headers = { 'accept-language' : 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7' }

    r = session.get( YOUTUBE_HOST_URL + browse_url, headers=headers )
    
    json_data = json.loads( r.text )
    channels_html = None
    try:
        channels_html = json_data['content_html']
    except:
        print( '[SShampoo] error occured, try one more time...', browse_url )
        return [], browse_url # try again

    soup = BeautifulSoup( channels_html, 'html.parser' )
    items = soup.select( 'div.yt-lockup-content' )

    channel_ids = []
    for item in items :
        channel_url = item.select( 'h3 > a' )[0]['href']
        channel_id = channel_url.split( '/')[-1]
        channel_ids.append( channel_id )

    # check more button
    next_browse_path = None
    LOAD_MORE_DATA_ID = 'load_more_widget_html'
    if LOAD_MORE_DATA_ID in json_data:
        load_more_html  = json_data[LOAD_MORE_DATA_ID]
        if load_more_html != None and len( load_more_html ) >0:              
            soup = BeautifulSoup( load_more_html, 'html.parser' )
            next_browse_path = soup.select( 'button' )[0]['data-uix-load-more-href']

    return channel_ids, next_browse_path


def check_subscription( channel_url, channel_id ):
    headers = { 'user-agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36' }

    session = requests.session()
    r = session.get( channel_url, headers=headers )

    initial_data, session_token = get_initial_data_of_youtube( r.text )

    json_data = json.loads( initial_data )
    
    grid_data = None
    tabs = json_data['contents']['twoColumnBrowseResultsRenderer']['tabs']
    for tab in tabs:
        try:
            grid_data = tab['tabRenderer']['content']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents'][0]['gridRenderer']
        except KeyError:
            continue
        
    if grid_data == None:
        print( '[SShampoo] can not read subscriptions...', channel_url )
        return False
            
    # check subscription
    subscriptions = grid_data['items']
    for subscription in subscriptions:
        if channel_id == subscription['gridChannelRenderer']['channelId']:
            return True

    # tokens for browsing channel subscription
    if 'continuations' not in grid_data:
        return False

    continuations = grid_data['continuations'][0]['nextContinuationData']
    ctoken = continuations['continuation']
    itct = continuations['clickTrackingParams']

    browse_url = '/browse_ajax?ctoken={0}&itct={1}'.format( ctoken, itct )

    while browse_url != None:
        channel_ids, browse_url = get_subscribed_channel_id( session, browse_url )
        if len( channel_ids ) <= 0:
            session = requests.session()
            print( '[SShampoo] reconnect session...' )

        if channel_id in channel_ids:
            return True

    return False


def get_tokens_for_comment_api( session, youtube_url ):

    headers = { 'user-agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36' }

    r = session.get( youtube_url, headers=headers )

    initial_data, session_token = get_initial_data_of_youtube( r.text )

    json_data = json.loads( initial_data )
    continuations = json_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][2]['itemSectionRenderer']['continuations'][0]['nextContinuationData']

    ctoken = continuations['continuation']
    itct = continuations['clickTrackingParams']

    channelId = json_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][1]['videoSecondaryInfoRenderer']['owner']['videoOwnerRenderer']['title']['runs'][0]['navigationEndpoint']['browseEndpoint']['browseId']
    return CommentTokens( ctoken, itct, session_token, channelId )


def get_candidates_from_comments_by_youtube_api( video_id, page_token, re_picks, api_key, check_time=False ):
    COMMENT_THREADS_API = 'https://www.googleapis.com/youtube/v3/commentThreads'

    params = {
        'videoId' : video_id,
        'part' : 'snippet',
        'key' : api_key,
        'textFormat' : 'plainText',
        'pageToken' : page_token
    }
    
    headers = {
        'referer': 'https://explorer.apis.google.com',
        'user-agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'
    }

    r = requests.get( COMMENT_THREADS_API, params=params, headers=headers )

    pick_re = re.compile( re_picks )
    email_re = re.compile( '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)' )

    json_data = json.loads( r.text )
    next_page_token = None
    if json_data.get( 'nextPageToken' ) != None:
        next_page_token = json_data['nextPageToken']

    comments = json_data['items']
    candidates = []
    for comment in comments:
        item = comment['snippet']['topLevelComment']['snippet']
        id = item['authorChannelUrl'].replace( 'http://www.youtube.com', '' )
        name = item['authorDisplayName']
        text = item['textDisplay']
        emails = email_re.findall( text )
        picks = pick_re.findall( text )
        
        time_str = item['publishedAt'] # 2020-02-12T15:10:51.000Z
        time_obj = datetime.datetime.strptime( time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        time_obj += datetime.timedelta(hours=9) # to kst
        if check_time:
            if time_obj.date().month == 2 and time_obj.date().day < 14:
                candidates.append( Candidate( id, name, set( picks ), text, emails ) )
            else:
                print( '[SShampoo] Error: timeout', name, time_obj )
        else:
            candidates.append( Candidate( id, name, set( picks ), text, emails ) )

    return candidates, next_page_token


def get_candidates_from_comments( session, comment_token, re_picks ):
    COMMENT_API = 'https://www.youtube.com/comment_service_ajax'

    headers = {
        'content-type' : 'application/x-www-form-urlencoded',
        'accept-language' : 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'referer': 'https://www.youtube.com/watch?v=VpMRW4bcMys',
    }

    params = {
        'action_get_comments' : 1,
        'pbj' : 1,
        'ctoken' : comment_token.ctoken,
        'continuation' : comment_token.ctoken,
        'itct' : comment_token.itct
    }

    data = { 'session_token' : comment_token.session_token }

    r = session.post( COMMENT_API, params=params, data=data, headers=headers )
    json_data       = json.loads( r.text )
    comment_html    = json_data['content_html']

    soup = BeautifulSoup( comment_html, 'html.parser' )
    items = soup.select( 'div.comment-renderer-content' )
    
    pick_re = re.compile( re_picks )
    email_re = re.compile( '([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)' )

    candidates = []
    for item in items : 
        names = item.select( 'div.comment-renderer-header > a' )
        id = names[0]['href']
        name = names[0].text

        comments = item.select( 'div.comment-renderer-text-content' )
        text = comments[0].text 

        emails = email_re.findall( text )
        picks = pick_re.findall( text )

        candidates.append( Candidate( id, name, set( picks ), text, emails ) )

    # check more button
    has_more_comment = False
    LOAD_MORE_DATA_ID = 'load_more_widget_html'
    if LOAD_MORE_DATA_ID in json_data:
        load_more_html  = json_data[LOAD_MORE_DATA_ID]
        tree = lxml.html.fromstring( load_more_html )
        more_button = tree.cssselect( 'button' )
        ctoken  = more_button[0].attrib['data-uix-load-more-post-body'].replace('page_token=', '')
        itct    = more_button[0].attrib['data-sessionlink'].replace('itct=', '')
        ctoken = urllib.parse.unquote( urllib.parse.unquote( ctoken ) ) # because of %253D
        comment_token.ctoken = ctoken # update tokens for next call
        comment_token.itct = itct
        has_more_comment = True

    return candidates, has_more_comment


def merge_candidates( candidates, new_candidates ):
    merged_candidates = candidates.copy()
    for id, candidate in new_candidates.items():
        if merged_candidates.get( id ) != None:
            print( '[SShampoo] merge failed - duplicate: \n{0}\n\n{1}'.format( merged_candidates.get(id), candidate ) )
        else:
            merged_candidates[ id ] = candidate 
    
    return merged_candidates


def collect_candidates_from_comments( youtube_url, re_picks, api_key ):
    s = requests.session()
    comment_token = get_tokens_for_comment_api( s, youtube_url )
    
    video_id = 'm6LNiUIN54U'
    page_token = ''
    candidates = [] 
    while True:
        if len( api_key ) > 0:
            new_candidates, page_token = get_candidates_from_comments_by_youtube_api( video_id, page_token, re_picks, api_key )
            candidates.extend( new_candidates ) 
            print( '[SShampoo] scraping candidates... ', len(candidates) )

            if page_token == None or len(page_token) <= 0:
                print( '[SShampoo] finish scraping: {0}'.format( len(candidates)) )
                break 

        else:
            new_candidates, has_more_comment = get_candidates_from_comments( s, comment_token, re_picks )
            candidates.extend( new_candidates ) 
            print( '[SShampoo] scraping candidates... ', len(candidates) )

            if has_more_comment is False:
                print( '[SShampoo] finish scraping: {0}'.format( len(candidates)) )
                break            
    
    return candidates, comment_token.channel_id


def write_text_file( path, text ):
    
    with open( path, 'w', encoding='UTF8' ) as file:
        file.write( text )
    print( '[SShampoo] write text file:', path )

        
def remove_candidates( candidates, remove_dict ):
    
    for idx in range( len(candidates)-1, -1, -1):       # iterate reverse order
        if remove_dict.get( candidates[idx].id ) != None:
            # print( '[SShampoo] remove winner from candidates: ', candidates[idx].name )
            del( candidates[idx] )
    

def atoi(text):
    return int(text) if text.isdigit() else text


def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    '''
    return [ atoi(c) for c in re.split(r'(\d+)', text) ]


def draw_lots( candidates, file_path='winners.xlsx' ):
    # collects candidates by picks
    pick_buckets = {}       
    for candidate in candidates:
        for pick in candidate.picks:
            if pick_buckets.get( pick, None ) is None:
                bucket = [ candidate ]
                pick_buckets[ pick ] = bucket
            else:
                pick_buckets.get( pick ).append( candidate )

    print( '\nWinners! -----------------------------------------\n' )
    draw_lots_list = []            # 2-dimentional list to save results into excel file
    winners = {}
    picks = [ *pick_buckets ]
    picks.sort( key=natural_keys ) # sort ascending order
    for pick in picks:
        candidates = pick_buckets.get( pick )
        remove_candidates( candidates, winners )    # remove winners to prevent multiple wins

        names = ''
        for candidate in candidates:
            names += candidate.name if len(names) <= 0 else ', ' + candidate.name 
        
        if len(candidates) <= 0:
            print( 'Pick: {0} - No one entered this event'.format( pick ) )
            print( '\n---------------\n')
            continue

        winning_number = random.randrange( len(candidates) )    # draw lots!
        winner = candidates[winning_number]
        winners[ winner.id ] = winner
        
        draw_lots_list.append( [ pick, len(candidates), names ] + winner.to_excel_row() )

        print( 'Pick: {0}'.format( pick ) )
        print( 'Candidates({0}): {1}'.format( len(candidates), names ) )
        print( 'Winner: {0} {1}'.format( winner.name, winner.emails ) )
        print( 'Comment: {0}'.format( winner.comment ) )
        print( '\n--------------------------------------------------\n' )

    write_xlsx_file( file_path, Candidate.excel_headers_for_winner(), draw_lots_list)


def write_xlsx_file( path, headers, data_matrix ):
    workbook    = xlsxwriter.Workbook( path )
    worksheet   = workbook.add_worksheet()
    
    # write headers
    POS_FORMAT = '{0}1' # ex. A1, B2
    header_column = 'A'
    bold = workbook.add_format( {'bold': True} )
    text_wrap = workbook.add_format( {'text_wrap': True} )
    for header in headers:
        worksheet.write( POS_FORMAT.format( header_column ), header['name'], bold )
        # add format
        if header.get( 'text_wrap' ) != None:
            worksheet.set_column( '{0}:{0}'.format( header_column ), None, text_wrap )
        if header.get( 'width' ) != None:
            worksheet.set_column( '{0}:{0}'.format( header_column ), header.get('width') )
       
        header_column = chr( ord(header_column) + 1 ) 
    
    for row_idx in range( 0, len( data_matrix ) ):
        columns = data_matrix[row_idx]
        for col_idx in range( 0, len( columns ) ):
            data = columns[col_idx]
            worksheet.write( row_idx+1, col_idx, data ) # +1 because of headers

    workbook.close()
    print( '[SShampoo] {0} file has been generated.'.format( path ) )


def save_candidates_to_xlsx_file( path, candidates ):
    data_matrix = []
    for candidate in candidates:
        data_matrix.append( candidate.to_excel_row() )

    write_xlsx_file( path, Candidate.excel_headers(), data_matrix )


def make_unique_candidate_list( candidates ):
    unique_list = []
    id_set = set( [] )
    for candidate in candidates:
        if candidate.id in id_set:
            continue
        
        unique_list.append( candidate )
        id_set.add( candidate.id )

    return unique_list


def check_subscription_by_youtube_api( candidate, channel_id, api_key ):
    subscriber_list = []

    SUBSCRIPTION_API = 'https://content.googleapis.com/youtube/v3/subscriptions'

    params = {
        'channelId' : candidate.id.split( '/' )[-1],
        'forChannelId' : channel_id,
        'part' : 'snippet',
        'key' : api_key
    }
    
    headers = {
        'referer': 'https://explorer.apis.google.com',
        'user-agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'
    }

    r = requests.get( SUBSCRIPTION_API, params=params, headers=headers )
    if r.status_code == 200:
        json_data = json.loads( r.text )
        if json_data['pageInfo']['totalResults'] > 0:
            return True

    return False


def make_subscribed_candidate_list( candidates, channel_id, apikey ):
    YOUTUBE_CHANNEL_URL_FORMAT = 'https://youtube.com{0}/channels?view=56&shelf_id=0'

    index_list = []
    subscriber_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}

        for idx in range( 0, len(candidates) ):
            candidate = candidates[idx]
            if len( apikey ) > 0:
                futures[ executor.submit( check_subscription_by_youtube_api, candidate, channel_id, apikey ) ] = idx
            else:
                youtube_channel_url = YOUTUBE_CHANNEL_URL_FORMAT.format( candidate.id )
                futures[ executor.submit( check_subscription, youtube_channel_url, channel_id ) ] = idx

        for future in concurrent.futures.as_completed(futures):
            idx = futures[ future ]
            try:
                if True == future.result():
                    index_list.append( idx )
                else:
                    print( '[SShampoo] delete unsubscribed user - ', candidates[idx].id )

            except Exception as exc:
                print('[SShampoo] %r generated an exception: %s' % (candidates[idx].id, exc))
    
        index_list.sort()
        for idx in index_list:
            subscriber_list.append( candidates[idx] )

    return subscriber_list


if __name__ == '__main__':
    SAMPLE_YOUTUBE_URL = 'https://www.youtube.com/watch?v=m6LNiUIN54U'

    parser = argparse.ArgumentParser()
    # without dash(-) means positional arguments
    parser.add_argument('url', metavar=SAMPLE_YOUTUBE_URL, help='youtube url that you want to scrape comments.')
    parser.add_argument('-u', '--unique', action='store_true', help='scarape only the recent comment from the same user')
    parser.add_argument('-p', '--picks', metavar='([0-9]+번)', default='', help="collect user's pick using this regular expression")
    parser.add_argument('-d', '--draw', action='store_true', help="draw lots using picks")
    parser.add_argument('-f', '--filename', metavar='comments', default='comments', help='file name of xlsx output file')
    parser.add_argument('-s', '--subscription', action='store_true', help='collect subscribers only')
    parser.add_argument('-k', '--apikey', metavar='AIzaSyAa8yy0GdcGPHdtD083HiGGx_S0vMPScDM', default='', help='youtube API key for checking subscription. Optional.')
    # get free key from https://developers.google.com/youtube/v3/docs/subscriptions/list?apix=true&apix_params=%7B%22part%22%3A%22snippet%22%2C%22channelId%22%3A%22UCHk5WmMQA7TL4aw3GhYi2CQ%22%2C%22forChannelId%22%3A%22UCojDgwOQ7UWBi10zL1GutEw%22%7D
    args = parser.parse_args()
    # args = parser.parse_args( ['https://www.youtube.com/watch?v=m6LNiUIN54U', '-p', '([0-9]+번)', '-u', '-d', '-s', '-k', 'AIzaSyAa8yy0GdcGPHdtD083HiGGx_S0vMPScDM'] )

    if None == args.url:
        print( 'Please, input youtube url. ex) python comment_scraper.py', SAMPLE_YOUTUBE_URL )
    else:
        print( '[SShampoo] start scraping...' )

        candidates, channel_id = collect_candidates_from_comments( args.url, args.picks, args.apikey )
        if args.unique:
            candidates = make_unique_candidate_list( candidates )

        XLSX_FILE_EXT = '.xlsx'
        save_candidates_to_xlsx_file( args.filename + XLSX_FILE_EXT, candidates )

        if args.subscription:
            candidates = make_subscribed_candidate_list( candidates, channel_id, args.apikey )           
            save_candidates_to_xlsx_file( args.filename + '_subscriber_only' + XLSX_FILE_EXT, candidates )
        
        print( '[SShampoo] total candidates:', len(candidates) )

        if args.draw:
            draw_lots( candidates, 'winners' + XLSX_FILE_EXT )

        print( '[SShampoo] Done!' )






   
                                





    