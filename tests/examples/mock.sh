kubectl run tmp-curl --rm -i --restart=Never --image=curlimages/curl -- sh -lc '
curl -sS -X POST \
    http://sre-copilot.default.svc.cluster.local:8000/webhook/alertmanager \
    -H "Content-Type: application/json" \
    -d "{
        \"status\":\"firing\",
        \"commonLabels\":{
            \"alertname\":\"KubePodCrashLooping\",
            \"severity\":\"warning\",
            \"service\":\"prometheus-alertmanager\",
            \"namespace\":\"monitoring\"
        },
        \"alerts\":[{
            \"status\":\"firing\",
            \"labels\":{\"pod\":\"alertmanager-main-0\"},
            \"annotations\":{\"summary\":\"Crash looping\"}
        }]
    }"
'