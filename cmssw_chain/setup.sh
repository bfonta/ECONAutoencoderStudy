WORKFLOW_BASE="${HOME}"/Documents/LLR/FPGAs/cmssw_chain
MY_AIRFLOW_BASE=/airflow

export AIRFLOW_HOME="${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"
export AIRFLOW__CORE__DAGS_FOLDER="${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"
export AIRFLOW__CORE__SQL_ALCHEMY_CONN=sqlite:///"${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"/airflow.db
export AIRFLOW__CORE__PLUGINS_FOLDER="${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"/plugins
export AIRFLOW__SCHEDULER__CHILD_PROCESS_LOG_DIRECTORY="${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"/logs/scheduler
export AIRFLOW__LOGGING__BASE_LOG_FOLDER="${WORKFLOW_BASE}${MY_AIRFLOW_BASE}"/logs

export PYTHONPATH="${PYTHONPATH}":"${WORKFLOW_BASE}"

airflow db init

airflow users create \
    --username admin \
    --firstname Bruno \
    --lastname Alves \
    --role Admin \
    --email bruno.alves@cern.ch

airflow scheduler

airflow webserver --port ${1:-8080} &
