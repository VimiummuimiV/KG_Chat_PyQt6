"""URL request interceptor for ad blocking"""
import re
from typing import Set, List
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt6.QtCore import QUrl


class AdBlocker(QWebEngineUrlRequestInterceptor):
    """Advanced ad blocker with pattern matching"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Counters
        self.blocked_count = 0
        self.allowed_count = 0
        
        # Compiled regex patterns for better performance
        self.blocked_patterns: List[re.Pattern] = []
        self.exception_patterns: List[re.Pattern] = []
        
        # Domain-based rules (faster than regex)
        self.blocked_domains: Set[str] = set()
        
        # Load built-in filters
        self._load_builtin_filters()
    
    def _load_builtin_filters(self):
        """Load comprehensive built-in ad/tracker blocking rules"""
        
        # Major ad networks and trackers
        domains = {
            # Google ecosystem
            'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
            'googletagservices.com', 'google-analytics.com', 'googletagmanager.com',
            'adservice.google.com', 'pagead2.googlesyndication.com',
            'tpc.googlesyndication.com', 'video-ad-stats.googlesyndication.com',
            
            # YouTube ads
            'youtube.com/api/stats/ads', 'youtube.com/pagead/',
            'youtube.com/ptracking', 'youtube.com/api/stats/qoe',
            'youtube.com/get_midroll_info',
            
            # Facebook/Meta
            'facebook.com/tr', 'connect.facebook.net', 'facebook.net/en_US/fbevents.js',
            'an.facebook.com', 'pixel.facebook.com',
            
            # Amazon
            'amazon-adsystem.com', 'advertising.amazon.com', 'aax.amazon-adsystem.com',
            
            # Major ad exchanges
            'adnxs.com', 'adsrvr.org', 'advertising.com', 'rubiconproject.com',
            'criteo.com', 'criteo.net', 'pubmatic.com', 'openx.net', 'contextweb.com',
            'casalemedia.com', 'indexww.com', 'smartadserver.com', 'improvedigital.com',
            
            # Content recommendation / Native ads
            'outbrain.com', 'outbrain.org', 'taboola.com', 'zemanta.com',
            'gravity.com', 'sharethrough.com', 'nativo.com', 'adblade.com',
            
            # Analytics & tracking
            'scorecardresearch.com', 'quantserve.com', 'quantcount.com',
            'mixpanel.com', 'hotjar.com', 'mouseflow.com', 'crazyegg.com',
            'segment.io', 'segment.com', 'fullstory.com', 'loggly.com',
            'chartbeat.com', 'chartbeat.net', 'newrelic.com',
            
            # Social trackers
            'twitter.com/i/adsct', 'analytics.twitter.com', 'static.ads-twitter.com',
            'linkedin.com/px', 'www.linkedin.com/px', 'px.ads.linkedin.com',
            'ads.linkedin.com', 'analytics.tiktok.com',
            
            # Ad verification / viewability
            'moatads.com', 'adsafeprotected.com', 'doubleverify.com',
            'integralads.com', 'voicefive.com', 'serving-sys.com',
            
            # More ad networks
            'adform.net', 'adform.com', 'admedo.com', 'adsco.re',
            'mathtag.com', 'exoclick.com', 'propellerads.com',
            'popads.net', 'popcash.net', 'bidswitch.net', 'bluekai.com',
            'eyeota.net', 'mediavoice.com', 'nexac.com', 'teads.tv',
            'tidaltv.com', 'turn.com', 'yieldmo.com', 'sovrn.com',
            'lijit.com', 'media.net', 'revcontent.com', 'aditude.com',
            
            # RTB & programmatic
            'appnexus.com', 'adtech.de', 'adtechus.com', 'advertising.com',
            'yieldlab.net', 'smartclip.net', 'vertamedia.com',
            
            # Mobile ads
            'unity3d.com/ad', 'chartboost.com', 'vungle.com', 'applovin.com',
            'startapp.com', 'inmobi.com', 'flurry.com',
            
            # Retargeting
            'adroll.com', 'rlcdn.com', 'perfectaudience.com', 'retargetly.com',
            
            # Pop-ups / Redirects
            'mgid.com', 'marketgid.com', 'revive-adserver.net',
            
            # Tracking pixels
            'pixel.quantserve.com', 'b.scorecardresearch.com', 'secure.quantserve.com',
            
            # CDN for ads
            '2mdn.net', 'gcdn.2mdn.net',
            
            # Imgur ads
            's.imgur.com/min/ad', 'imgur.com/ads',
            
            # Reddit ads
            'redd.it/pixel', 'alb.reddit.com',
            
            # Video ad platforms
            'videoadex.com', 'spotxchange.com', 'spotx.tv', 'tremorhub.com',
            'yume.com', 'innovid.com', 'tremormedia.com',
        }
        
        self.blocked_domains.update(domains)
        
        # URL patterns (converted to regex for flexible matching)
        patterns = [
            # Ad-related paths
            r'/pagead/', r'/ads/', r'/ad/', r'/adview', r'/ad_status',
            r'/adsense', r'/adservice', r'/advertisement',
            
            # Separators
            r'[_\-\.]ads?[_\-\.]', r'[_\-\.]ad[_\-\.]',
            
            # Analytics
            r'/analytics', r'/tracking', r'/tracker', r'/track/',
            r'/collect', r'/beacon', r'/pixel', r'/impression',
            
            # Google specific
            r'/doubleclick', r'/googleads', r'/generate_204',
            
            # Ad scripts
            r'adsbygoogle', r'show_ads', r'adserver', r'adsystem',
            
            # Common ad files
            r'[_\-\.]banner[_\-\.]', r'/banners?/', r'/advert',
            
            # Popups
            r'/popup', r'/popunder',
            
            # Sponsored content
            r'/sponsored', r'/promo/',
            
            # Video ads
            r'/preroll', r'/midroll', r'/videoplayback.*adformat',
            
            # Affiliate
            r'/affiliate', r'/aff_',
        ]
        
        # Compile patterns
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        
        # Exception patterns (things we DON'T want to block)
        # These override blocking rules
        exceptions = [
            r'youtube\.com/(?!pagead|ptracking|api/stats)',  # Allow YouTube except ads
            r'cdn\.', r'static\.', r'assets\.',  # Usually legitimate content
        ]
        
        self.exception_patterns = [re.compile(p, re.IGNORECASE) for p in exceptions]
    
    def interceptRequest(self, info):
        """Intercept and potentially block requests"""
        url = info.requestUrl()
        url_string = url.toString()
        url_lower = url_string.lower()
        host = url.host().lower()
        
        # Check exception patterns first (allow overrides block)
        for pattern in self.exception_patterns:
            if pattern.search(url_string):
                self.allowed_count += 1
                return
        
        # Check blocked domains (fastest check)
        for blocked_domain in self.blocked_domains:
            if blocked_domain in host or host.endswith('.' + blocked_domain):
                info.block(True)
                self.blocked_count += 1
                # print(f"🚫 Blocked domain: {host}")  # Debug
                return
        
        # Check regex patterns
        for pattern in self.blocked_patterns:
            if pattern.search(url_lower):
                info.block(True)
                self.blocked_count += 1
                # print(f"🚫 Blocked pattern: {url_string[:80]}...")  # Debug
                return
        
        self.allowed_count += 1
    
    def get_blocked_count(self):
        """Get number of blocked requests"""
        return self.blocked_count
    
    def get_allowed_count(self):
        """Get number of allowed requests"""
        return self.allowed_count
    
    def get_stats(self):
        """Get blocking statistics"""
        total = self.blocked_count + self.allowed_count
        if total == 0:
            return "No requests processed"
        
        block_percent = (self.blocked_count / total) * 100
        return f"Blocked {self.blocked_count}/{total} ({block_percent:.1f}%)"
    
    def reset_stats(self):
        """Reset all counters"""
        self.blocked_count = 0
        self.allowed_count = 0