#!/bin/bash
set -eu

# Declare variables
GCLOUD=$(which gcloud)
SED=$(which sed)
KUBECTL=$(which kubectl)
GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
CLUSTER='merino-locust-load-test'
TARGET='https://stagepy.merino.nonprod.cloudops.mozgcp.net'
SCOPE='https://www.googleapis.com/auth/cloud-platform'
REGION='us-west1'
WORKER_COUNT=5
MACHINE_TYPE='n1-standard-2'
BOLD=$(tput bold)
NORM=$(tput sgr0)
DIRECTORY=$(pwd)

MERINO_DIRECTORY=$DIRECTORY/tests/load/kubernetes-config
MASTER_FILE=locust-master-controller.yml
WORKER_FILE=locust-worker-controller.yml
SERVICE_FILE=locust-master-service.yml

LOCUST_IMAGE_TAG=$(git log -1 --pretty=format:%h)
echo "Docker image tag for locust is set to: ${LOCUST_IMAGE_TAG}"

##Declare variables to be replaced later in the YAML file using the sed commands
MERINO_REMOTE_SETTINGS__SERVER='https://firefox.settings.services.mozilla.com'
MERINO_REMOTE_SETTINGS__COLLECTION=quicksuggest
MERINO_REMOTE_SETTINGS__BUCKET=main
MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH='dev/top_picks.json'
MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT='4'
MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT='2'
MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY=''
MERINO_PROVIDERS__WIKIPEDIA__ES_URL='https://merino-nonprod.es.us-west1.gcp.cloud.es.io:9243'
MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX='enwiki-v1'

SetupGksCluster()
{

    #Configure Kubernetes
    echo -e "==================== Prepare environments with set of environment variables "
    echo -e "==================== Set Kubernetes Cluster "
    export CLUSTER=$CLUSTER
    echo -e "==================== Set Kubernetes TARGET "
    export TARGET=$TARGET
    echo -e "==================== Set SCOPE "
    export SCOPE=$SCOPE

    echo -e "==================== Refresh Kubeconfig at path ~/.kube/config "
    $GCLOUD container clusters get-credentials $CLUSTER --region $REGION --project $GOOGLE_CLOUD_PROJECT

    ##Build Docker Images
    echo -e "==================== Build the Docker image and store it in your project's container registry. Tag with the latest commit hash "
    $GCLOUD builds submit --config=./tests/load/cloudbuild.yaml --substitutions=TAG_NAME=$LOCUST_IMAGE_TAG
    echo -e "==================== Verify that the Docker image is in your project's container repository"
    $GCLOUD container images list | grep locust-merino

    ##Deploying the Locust master and worker nodes
    echo -e "==================== Update Kubernetes Manifests "
    echo -e "==================== Replace the target host and project ID with the deployed endpoint and project ID in the locust-master-controller.yml and locust-worker-controller.yml files"

    FILES=($MASTER_FILE $WORKER_FILE)
    for file in "${FILES[@]}"
    do
        $SED -i -e "s|\[TARGET_HOST\]|$TARGET|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[PROJECT_ID\]|$GOOGLE_CLOUD_PROJECT|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[LOCUST_IMAGE_TAG\]|$LOCUST_IMAGE_TAG|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_REMOTE_SETTINGS__BUCKET\]|$MERINO_REMOTE_SETTINGS__BUCKET|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_REMOTE_SETTINGS__COLLECTION\]|$MERINO_REMOTE_SETTINGS__COLLECTION|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_REMOTE_SETTINGS__SERVER\]|$MERINO_REMOTE_SETTINGS__SERVER|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[WORKER_COUNT\]|$WORKER_COUNT|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH\]|$MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT\]|$MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT\]|$MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY\]|$MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__WIKIPEDIA__ES_URL\]|$MERINO_PROVIDERS__WIKIPEDIA__ES_URL|g" $MERINO_DIRECTORY/$file
        $SED -i -e "s|\[MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX\]|$MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX|g" $MERINO_DIRECTORY/$file

    done

    ##Deploy the Locust master and worker nodes using Kubernetes Manifests
    echo -e "==================== Deploy the Locust master and worker nodes"
    $KUBECTL apply -f $MERINO_DIRECTORY/$MASTER_FILE
    $KUBECTL apply -f $MERINO_DIRECTORY/$SERVICE_FILE
    $KUBECTL apply -f $MERINO_DIRECTORY/$WORKER_FILE

    echo -e "==================== Verify the Locust deployments & Services"
    $KUBECTL get pods -o wide
    $KUBECTL get services
}

echo "==================== The script is used to create & delete the GKE cluster"
echo "==================== Do you want to create or setup the existing or delete GKE cluster? Select ${BOLD}create or delete or setup ${NORM}"
while :
do
    read response
    case $response in
        create) #Setup Kubernetes Cluster
            echo -e "==================== Creating the GKE cluster "
            $GCLOUD container clusters create $CLUSTER --region $REGION --scopes $SCOPE --enable-autoscaling --min-nodes "5" --max-nodes "10" --scopes=logging-write,storage-ro --addons HorizontalPodAutoscaling,HttpLoadBalancing  --machine-type $MACHINE_TYPE
            SetupGksCluster
            break
            ;;
        delete)
            echo -e "==================== Delete the GKE cluster "
            $GCLOUD container clusters delete $CLUSTER --region $REGION
            break
            ;;
        setup)
            echo -e "==================== Setup the GKE cluster "
            SetupGksCluster
            break
            ;;
        *)
            echo -e "==================== Incorrect input! "
            break
            ;;
    esac
done
