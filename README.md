* Create Livekit configuration (for local usage):
```shell
  `$ docker run -it --rm -v$(pwd):/output livekit/generate --local`
```
  or use existing one
```yaml
port: 7880
rtc:
    udp_port: 7882
    tcp_port: 7881
    port_range_start: 50000
    port_range_end:   50199
keys:
    APIAr4ziPRxD7RQ: NG4BDigFkZpjXZrJ7oPfHd9p0WdxPLuffJcAKUHJjKfC
logging:
    json: false
    level: info
redis:
  address: redis:6379
```

* set up `uv` package manager:
```shell
pip install uv
```

* Set up environment variables (host context to be used by `lk` CLI utility):
```shell
export LIVEKIT_URL=ws://localhost:7880
export LIVEKIT_API_SECRET=NG4BDigFkZpjXZrJ7oPfHd9p0WdxPLuffJcAKUHJjKfC
export LIVEKIT_API_KEY=APIAr4ziPRxD7RQ
```

* Set up python dependencoes/requirements:
```shell
sudo dnf install mariadb-connector-c-devel
pip install --upgrade pip
pip install \
    "livekit-agents[all]" \
    "livekit-plugins-openai" \
    "livekit-plugins-deepgram" \
    mcp \
    mariadb \
    httpx \
    fastapi \
    uvicorn
```

* Start services (containers)
```shell
docker compose up
```

* Prepare database table and populate it: wtart DB service running, connect to it and apply following SQL script
```shell
docker exec -it $(docker ps -qf "name=mariadb") mariadb -u livekit_user -plivekit_pass livekit_db
```
```sql
CREATE TABLE users (
  user_id INT PRIMARY KEY,
  balance_value DECIMAL(10,2) NOT NULL
);
INSERT INTO users (user_id, balance_value) VALUES (123, 1000.50), (456, 2500.00);
SELECT * FROM users;
EXIT;
```

* Check if `redis` service is ready
```shell
docker exec -it $(docker ps -qf "name=redis") redis-cli ping
```

* Check if `mariadb` service is runnig
```shell
docker exec -it $(docker ps -qf "name=mariadb") mariadb -u livekit_user -plivekit_pass livekit_db -e "SELECT * FROM users;"
```

* Download LLM
```shell
docker exec -it $(docker ps -qf "name=ollama") ollama pull llama3.2:3b-instruct-q4_K_M
```

* Create dispatch rule (you need to have environment variables `LIVEKIT_URL`, `LIVEKIT_API_SECRET`, `LIVEKIT_API_KEY` mentioned above to be set)
```shell
cat > dispatch-rule-01.json << EOF
{
  "dispatch_rule": {
    "rule": {
      "dispatchRuleIndividual": {
        "roomPrefix": "test-"
      }
    },
    "roomConfig": {
      "agents": [
        {
          "agentName": "voice-agent"
        }
      ]
    }
  }
}
EOF
lk sip dispatch create dispatch-rule-01.json
```

* Check if dispatch rule is set up properly
```shell
lk sip dispatch list
```

* Set up SIP client (`https://www.zoiper.com/en/voip-softphone/download/current`)
  SIP account (you must to use main host network interface IP address, not localhost):
      * Username: testtrunk
      * Password: testpass
      * Domain: 192.168.31.41:5060

* Set up SIP client (`https://www.linphone.org/en/homepage-linphone/`)
    SIP account (you must to use main host network interface IP address, not localhost):
      * Displayname" sip-test
      * Username: sip-test



