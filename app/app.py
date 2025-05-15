from flask import Flask, render_template, request, redirect, url_for
import re
from pathlib import Path
import subprocess
import os



#

DNSDIST_CONFIG_PATH = "/etc/dnsdist/dnsdist.conf"
DNSMASQ_CONFIG_PATH = "/root/sniproxy-wg/dnsmasq.conf"

# We Assume 1 Thing Here: below variable MUST! exist in dnsdist.conf  
# subnets             :       list of subnets we want to proxy with SNI



subnets = []
domains = []


app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():

    global subnets, domains

        # Check if dnsdist.conf exists, if it didnt return error.
    if not Path(DNSDIST_CONFIG_PATH).exists(): raise FileNotFoundError(f"{DNSDIST_CONFIG_PATH} File Dosent Exist!") 


    # Read dnsdsit config content and find subnets
    with open(DNSDIST_CONFIG_PATH, "r") as dnsdist_config:
        lines = dnsdist_config.readlines()

        proxy_str = ""
        flag_proxy = False

        for line in lines:

            if "subnets" in line: flag_proxy = True
            if flag_proxy == True and re.match(r'[a-z]', line) == None: proxy_str += line
            if "}" in line: flag_proxy = False

        # read each subnet from the string block and add to the list 
        
        subnets = re.findall(r'"([^"]*)"', proxy_str)


    # Read dnsmasq.conf and parse the domains
    with open(DNSMASQ_CONFIG_PATH, "r") as dnsmasq_config:

        # Other Lines of dnsmasq.conf execpt domains
        domains = []
        lines = dnsmasq_config.readlines()
        for line in lines:
            domain = re.findall(r'address=/([^/]+)/\{SNI_HOST_IP\}', line)
            if domain: domains += domain
        


    return render_template(
        'index.html',
        left_text="\n".join(subnets),
        right_text="\n".join(domains)
    )




@app.route('/submit_left', methods=['POST'])
def submit_left():
    global domains, subnets
    submitted_text = request.form.get('left_textarea', '')
    subnets = [line.strip() for line in submitted_text.strip().split('\n') if line.strip()]

    conf = "local subnets = {\n"
    for subnet in subnets: 
        conf += '"' + subnet + '",\n'
    conf += "}\n"

    default = f"""
setLocal('0.0.0.0:53')
setACL('0.0.0.0/0')

webserver('0.0.0.0:5353')
setWebserverConfig({{password="1234", apiKey="12345", acl="0.0.0.0/0"}})

newServer({{address = '127.0.0.1:530', pool='sniproxy'}})
addAction(NetmaskGroupRule(subnets), PoolAction("sniproxy"))

"""
    conf += default
    
    with open(DNSDIST_CONFIG_PATH + "-temp", "w") as temp:
        temp.writelines(conf)
    command = subprocess.run(f"dnsdist --check-config -C {DNSDIST_CONFIG_PATH}-temp", shell=True, text=True, capture_output=True)
    if re.match(f"Configuration {DNSDIST_CONFIG_PATH}-temp OK!", command.stdout): os.remove(f"{DNSDIST_CONFIG_PATH}-temp")
    with open(DNSDIST_CONFIG_PATH, "w") as config : config.writelines(conf) 
    subprocess.run("systemctl restart dnsdist", shell=True, text=True)

    domains = []
    subnets = []

    return redirect(url_for('index'))

@app.route('/submit_right', methods=['POST'])
def submit_right():
    global domains, subnets
    submitted_text = request.form.get('right_textarea', '')
    domains = [line.strip() for line in submitted_text.strip().split('\n') if line.strip()]

    conf = """
bind-dynamic
bogus-priv
domain-needed
log-queries
log-facility=-
#log-facility=/dnsmasq.log
local-ttl=60
server={DNS_PROXY_IP}
"""
    
    for domain in domains:
        conf += f"address=/{domain}/{{SNI_HOST_IP}}\n"

    with open(DNSMASQ_CONFIG_PATH, "w") as config: config.writelines(conf)
    subprocess.run("docker restart sni", text=True, shell=True)

    #TODO: restart the container of dnsmasq or reload it somehow.

    domains = []
    subnets = []
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
