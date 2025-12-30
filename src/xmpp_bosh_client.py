import requests
import xml.etree.ElementTree as ET
import base64
import random
from accounts import AccountManager

class XMPPBoshClient:
    """XMPP BOSH Client with account management"""
    
    def __init__(self, config_path: str = 'config.json'):
        self.account_manager = AccountManager(config_path)
        self.rid = int(random.random() * 1e10)
        self.sid = None
        self.jid = None
        
        # Load configurations
        server = self.account_manager.get_server_config()
        self.url = server.get('url')
        self.domain = server.get('domain')
        self.resource = server.get('resource')
        
        conn = self.account_manager.get_connection_config()
        self.conn_params = {
            'xml:lang': conn.get('lang', 'en'),
            'wait': conn.get('wait', '60'),
            'hold': conn.get('hold', '1'),
            'content': conn.get('content_type', 'text/xml; charset=utf-8'),
            'ver': conn.get('version', '1.6'),
            'xmpp:version': conn.get('xmpp_version', '1.0')
        }
        
        self.headers = {
            'Content-Type': 'text/xml; charset=UTF-8',
            'Origin': 'https://klavogonki.ru',
            'Referer': 'https://klavogonki.ru/gamelist/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def build_bosh_body(self, children=None, **attrs):
        """Build BOSH body element with proper namespaces"""
        body = ET.Element('body', {
            'rid': str(self.rid),
            'xmlns': 'http://jabber.org/protocol/httpbind',
            **{k: v for k, v in attrs.items() if v is not None}
        })
        if self.sid:
            body.set('sid', self.sid)
        if any(k.startswith('xmpp:') for k in attrs):
            body.set('xmlns:xmpp', 'urn:xmpp:xbosh')
        if children:
            for child in children:
                body.append(child)
        return ET.tostring(body, encoding='utf-8').decode('utf-8')
    
    def send_request(self, payload):
        """Send BOSH request and return response"""
        print(f"\n📤 Sending:\n{payload}")
        response = requests.post(self.url, data=payload, headers=self.headers)
        response.raise_for_status()
        print(f"📥 Response:\n{response.text}")
        return response.text
    
    def parse_xml(self, xml_text):
        """Parse XML response safely"""
        try:
            return ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"❌ Parse error: {e}")
            return None
    
    def connect(self, account=None):
        """Connect using specified account or active account"""
        # Get account
        if account is None:
            account = self.account_manager.get_active_account()
        elif isinstance(account, str):
            # Login provided
            account = self.account_manager.get_account_by_login(account)
        
        if not account:
            return print("❌ No account found")
        
        print(f"\n🔑 Connecting as: {account['login']} (ID: {account['user_id']})")
        
        user_id = account['user_id']
        login = account['login']
        password = account['password']
        
        # 🔌 Step 1: Initialize BOSH session
        payload = self.build_bosh_body(to=self.domain, **self.conn_params)
        root = self.parse_xml(self.send_request(payload))
        if root is not None:
            self.sid = root.get('sid')
            print(f"\n✅ Session ID: {self.sid}")
        
        if not self.sid:
            return print("❌ Failed to obtain SID")
        
        # 🔐 Step 2: SASL PLAIN authentication
        self.rid += 1
        authcid = f'{user_id}#{login}'
        auth_str = f'\0{authcid}\0{password}'
        auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('ascii')
        
        auth_elem = ET.Element('auth', {
            'xmlns': 'urn:ietf:params:xml:ns:xmpp-sasl',
            'mechanism': 'PLAIN'
        })
        auth_elem.text = auth_b64
        
        self.send_request(self.build_bosh_body(children=[auth_elem]))
        
        # 🔄 Step 3: Restart XMPP stream
        self.rid += 1
        payload = self.build_bosh_body(**{
            'xmpp:restart': 'true',
            'to': self.domain,
            'xml:lang': 'en'
        })
        self.send_request(payload)
        
        # 🏷️ Step 4: Bind resource and get JID
        self.rid += 1
        iq = ET.Element('iq', {'type': 'set', 'id': 'bind_1', 'xmlns': 'jabber:client'})
        bind = ET.SubElement(iq, 'bind', {'xmlns': 'urn:ietf:params:xml:ns:xmpp-bind'})
        ET.SubElement(bind, 'resource').text = self.resource
        
        root = self.parse_xml(self.send_request(self.build_bosh_body(children=[iq])))
        if root is not None:
            jid_el = root.find('.//{urn:ietf:params:xml:ns:xmpp-bind}jid')
            if jid_el is not None:
                self.jid = jid_el.text
                print(f"\n✅ Bound JID: {self.jid}")
        
        if not self.jid:
            return print("❌ Failed to bind JID")
        
        # 📝 Step 5: Establish session
        self.rid += 1
        iq = ET.Element('iq', {'type': 'set', 'id': 'session_1', 'xmlns': 'jabber:client'})
        ET.SubElement(iq, 'session', {'xmlns': 'urn:ietf:params:xml:ns:xmpp-session'})
        self.send_request(self.build_bosh_body(children=[iq]))
        
        return True
    
    def join_room(self, room_jid, nickname=None):
        """Join a MUC room"""
        account = self.account_manager.get_active_account()
        if nickname is None:
            nickname = f"{account['user_id']}#{account['login']}"
        
        # 🚪 Step 6: Join MUC room
        self.rid += 1
        presence = ET.Element('presence', {
            'xmlns': 'jabber:client',
            'to': f'{room_jid}/{nickname}'
        })
        ET.SubElement(presence, 'x', {'xmlns': 'http://jabber.org/protocol/muc'})
        
        # Add userdata
        x_data = ET.SubElement(presence, 'x', {'xmlns': 'klavogonki:userdata'})
        user = ET.SubElement(x_data, 'user')
        ET.SubElement(user, 'login').text = account['login']
        
        self.send_request(self.build_bosh_body(children=[presence]))
        
        print(f"\n🎉 Joined room: {room_jid}")
    
    def listen(self):
        """Listen for incoming messages in real-time"""
        print("📡 Listening for messages...\n")
        
        try:
            while True:
                self.rid += 1
                response = self.send_request(self.build_bosh_body())
                root = self.parse_xml(response)
                
                if root is not None:
                    # Check if session was terminated
                    if root.get('type') == 'terminate':
                        print("\n⚠️  Session terminated by server")
                        break
                    
                    # Parse incoming messages
                    for message in root.findall('.//{jabber:client}message'):
                        from_jid = message.get('from', '')
                        body = message.find('{jabber:client}body')
                        if body is not None and body.text:
                            print(f"\n💬 [{from_jid}]: {body.text}")
                    
                    # Parse presence updates
                    for presence in root.findall('.//{jabber:client}presence'):
                        from_jid = presence.get('from', '')
                        ptype = presence.get('type', 'available')
                        if ptype != 'available':
                            print(f"👤 {from_jid} is now {ptype}")
        
        except KeyboardInterrupt:
            print("\n\n👋 Disconnecting...")
        except Exception as e:
            print(f"\n❌ Connection error: {e}")


def main():
    # Initialize client
    client = XMPPBoshClient()
    
    # Show interactive menu and get selected account
    selected = client.account_manager.interactive_menu()
    
    if selected == "exit" or selected is None:
        return
    
    # Connect with selected account
    if client.connect():
        # Auto-join rooms
        rooms = client.account_manager.get_rooms()
        for room in rooms:
            if room.get('auto_join', False):
                client.join_room(room['jid'])
        
        # Start listening
        client.listen()


if __name__ == "__main__":
    main()