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
        return [ 'Name', 'Email', 'Comment', 'Channel Url', 'Pick' ]


class CommentTokens(object):
    """CommentTokens"""

    def __init__(self, ctoken, itct, session_token):
        self.ctoken = ctoken
        self.itct = itct
        self.session_token = session_token

    def dump(self):
        print( '[SShampoo] CommentTokens - ctoken: {0}, itct: {1}, session_token: {2}'.format( self.ctoken, self.itct, self.session_token ) )


def get_tokens_for_comment_api( session, youtube_url ):

    headers = { 'user-agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36' }

    r = session.get( youtube_url, headers=headers )

    INIT_DAT_PREFIX         = 'window["ytInitialData"] ='
    SESSION_TOKEN_PREFIX    = '"XSRF_TOKEN":"'

    session_token = None
    json_string = ''
    lines = r.text.splitlines()
    for line in lines:
        line = line.strip()
        if session_token is None and line.find( SESSION_TOKEN_PREFIX ) > 0:
            start = line.find( SESSION_TOKEN_PREFIX ) + len( SESSION_TOKEN_PREFIX )
            end = line.find( '",', start )
            session_token = line[start:end]         

        if line.startswith( INIT_DAT_PREFIX ) :
            json_string = line[ len(INIT_DAT_PREFIX) : -1 ]
            break

    json_data = json.loads( json_string )
    continuations = json_data['contents']['twoColumnWatchNextResults']['results']['results']['contents'][2]['itemSectionRenderer']['continuations'][0]['nextContinuationData']

    ctoken = continuations['continuation']
    itct = continuations['clickTrackingParams']

    return CommentTokens( ctoken, itct, session_token )


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


def collect_candidates_from_comments( youtube_url, re_picks ):
    s = requests.session()
    comment_token = get_tokens_for_comment_api( s, youtube_url )

    candidates = [] 
    while True:
        new_candidates, has_more_comment = get_candidates_from_comments( s, comment_token, re_picks )
        candidates.extend( new_candidates ) 
        print( '[SShampoo] scraping candidates... ', len(candidates) )

        if has_more_comment is False:
            print( '[SShampoo] finish scraping: {0}'.format( len(candidates)) )
            break            
    
    return candidates


def write_text_file( path, text ):
    
    with open( path, 'w', encoding='UTF8' ) as file:
        file.write( text )
    print( '[SShampoo] write text file:', path )

        
def remove_candidates( candidates, remove_dict ):
    
    for idx in range( len(candidates)-1, -1, -1):       # iterate reverse order
        if remove_dict.get( candidates[idx].id ) != None:
            print( '[SShampoo] remove winner from candidates: ', candidates[idx].name )
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

    result_text = ''
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

        result_text += 'Pick: {0}\n'.format( pick )
        result_text += 'Candidates({0}): {1}\n'.format( len(candidates), names )
        result_text += 'Winner: {0} {1}\n'.format( winner.name, winner.emails )
        result_text += 'Comment: {0}\n'.format( winner.comment )
        result_text += '\n\n--------------------------------------------------\n\n'
    
    print( result_text )

    xlsx_headers = [ 'Pick', 'The number of candidates', 'Candidates' ]
    for header in Candidate.excel_headers():
        xlsx_headers.append( "Winner's " + header )

    write_xlsx_file( file_path, xlsx_headers, draw_lots_list)


def write_xlsx_file( path, headers, data_matrix ):
    workbook    = xlsxwriter.Workbook( path )
    worksheet   = workbook.add_worksheet()
    
    # write headers
    POS_FORMAT = '{0}1' # ex. A1, B2
    header_column = 'A'
    bold = workbook.add_format( {'bold': True} )
    for header in headers:
        worksheet.write( POS_FORMAT.format( header_column ), header, bold )
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


if __name__ == '__main__':
    SAMPLE_YOUTUBE_URL = 'https://www.youtube.com/watch?v=m6LNiUIN54U'

    parser = argparse.ArgumentParser()
    # without dash(-) means positional arguments
    parser.add_argument('url', metavar=SAMPLE_YOUTUBE_URL, help='youtube url that you want to scrape comments.')
    parser.add_argument('-u', '--unique', action='store_true', help='scarape only the recent comment from the same user')
    parser.add_argument('-p', '--picks', metavar='([0-9]+번)', default='', help="collect user's pick using this regular expression")
    parser.add_argument('-d', '--draw', action='store_true', help="draw lots using picks")
    parser.add_argument('-f', '--filename', metavar='comments', default='comments', help='file name of xlsx output file')
    args = parser.parse_args()
    #args = parser.parse_args( ['https://www.youtube.com/watch?v=m6LNiUIN54U', '-p', '([0-9]+번)', '-u', '-d'] )

    if None == args.url:
        print( 'Please, input youtube url. ex) python comment_scraper.py', SAMPLE_YOUTUBE_URL )
    else:
        print( '[SShampoo] start scraping...' )

        candidates = collect_candidates_from_comments( args.url, args.picks )
        if args.unique:
            candidates = make_unique_candidate_list( candidates )
        
        XLSX_FILE_EXT = '.xlsx'
        save_candidates_to_xlsx_file( args.filename + XLSX_FILE_EXT, candidates )
        print( '[SShampoo] total candidates:', len(candidates) )

        if args.draw:
            draw_lots( candidates, 'winners' + XLSX_FILE_EXT )

        print( '[SShampoo] Done!' )






   
                                





    