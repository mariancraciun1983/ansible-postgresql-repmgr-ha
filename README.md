<h1 align="center">PostgreSQL and Repmgr for High Availability and automated load balancing with HAProxy, Corosync and Pacemaker</h1>
<br />

<div align="center">
  <a href="https://travis-ci.com/mariancraciun1983/ansible-postgresql-repmgr-ha">
    <img src="https://travis-ci.com/mariancraciun1983/ansible-postgresql-repmgr-ha.svg?branch=master" alt="Build Status" />
  </a>
  <a href="https://galaxy.ansible.com/mariancraciun1983/postgres_repmgr_ha">
    <img src="https://img.shields.io/ansible/role/51810" alt="Ansible Galaxy" />
  </a>
  <a href="https://galaxy.ansible.com/mariancraciun1983/postgres_repmgr_ha">
    <img src="https://img.shields.io/ansible/quality/51810" alt="Ansible Quality Score" />
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License" />
  </a>
</div>
<br />



## Introduction

  Ansible role to configure PostgreSQL, Repmgr for High Availability
    and automated load balancing with HAProxy, Corosync and Pacemaker


## Automated replication and failover

The base functionality offer by the role is to configure the PostgreSQL cluster with replication monitored
by Repmgr. 
You will need to have, ideally, 3 nodes in order to satisfy the qorum size.

Each node should have the `postgres_role` set to `master` (exactly 1)  and `slave` (2 or more)
```yaml
  host_vars:
    node1:
      postgres_role: master
    node2:
      postgres_role: slave
    node3:
      postgres_role: slave
```

The role will work out of the box, with standard master-slave replication, with no configuration needed. Check [defaults/main.yml](./defaults/main.yml) for optional config vars.

To check the replication status , login as postgres and run:
```
postgres@node1:~$ psql -Aqtc "SELECT count(*) FROM pg_stat_replication"
2
```

## Managed Replication using Repmgr

repmgr is an open-source tool suite for managing replication and failover in a cluster of PostgreSQL servers. It enhances PostgreSQL's built-in hot-standby capabilities with tools to set up standby servers, monitor replication, and perform administrative tasks such as failover or manual switchover operations.

In order to turn on the installation and configuration using repmgr, set `postgres_repmgr_enabled` group variable to true:

```yaml
group_vars:
  postgres_repmgr_enabled: true
```

This will be using repmgr instead of pg_basebackup to clone the master and than register it in the repmgr cluster.

Once configured, you can check the replication status via repmgr as follows:
```
postgres@node1:~$ repmgr -f /etc/repmgr.conf cluster crosscheck
INFO: connecting to database
 Name  | ID | 1 | 2 | 3
-------------+----+---+---+---
 node1 | 1  | * | * | * 
 node2 | 2  | * | * | * 
 node3 | 3  | * | * | * 


postgres@node1:~$ repmgr -f /etc/repmgr.conf cluster show
 ID | Name        | Role    | Status    | Upstream    | Location | Priority | Timeline | Connection string                                          
----+-------------+---------+-----------+-------------+----------+----------+----------+-------------------------------------------------------------
 1  | node1 | primary | * running |       | default  | 100      | 1        | host=172.17.0.3 dbname=repmgr user=repmgr connect_timeout=2
 2  | node2 | standby |   running | node1 | default  | 100      | 1        | host=172.17.0.4 dbname=repmgr user=repmgr connect_timeout=2
 3  | node3 | standby |   running | node1 | default  | 100      | 1        | host=172.17.0.5 dbname=repmgr user=repmgr connect_timeout=2

```


## Load Balancing and Automated Failover

Repmgr will ensure that the replication remains functional by choosing a new master (primary) and adjusting the replication slave (master) targets.
The clients won't know however, which is the master and which is the server unless they do some discovery (ex: check replication status).


The approach found in this role takes advantage of the Corosync/Pacemaker to manage iptables rules, by automatically blocking writes on the slaves Repmgr Sentinel triggers failover events.


- each node will listen on 3 ports 5432 (default), 5434(RO), 5435 (RW), last 2 via iptables prerouting
- the master will have `postgres_role=master` corosync note attribute and `postgres_role=slave` for slaves respectivelly
- corosync will block port 5435 when redis_role=replica
- corosync will block port 5435 and 5434 when redis_role=fail
- the load balancer will try 5435 port for RW and only one server will NOT reject the connections `postgres_role=master`


### Requirements
The nodes should have Corosync with Pacemaker already configured. Check my [corosync_pacemaker ansible role](https://github.com/mariancraciun1983/ansible-corosync-pacemaker) . Having `symmetric-cluster` is also required so that not all nodes will get the resources assigned to them, but only based on pacemaker colocation rules.

`playbook.yml`:

```yaml
- name: Prepare Corosync/Pacemaker
  hosts: all
  gather_facts: true
  roles:
    - mariancraciun1983.corosync_pacemaker
    - mariancraciun1983.postgres_repmgr_ha
```

group_vars/all.yml
```yaml
# corosync config
install_python3: true
corosync_hacluster_password: 1q2w3e4r5t
corosync_cluster_settings:
  - key: stonith-enabled
    value: "false"
  - key: no-quorum-policy
    value: ignore
  - key: start-failure-is-fatal
    value: "false"
  - key: symmetric-cluster
    value: "false"

# enable repmgr
postgres_repmgr_enabled: true
# enable repmgr integration with pacemaker
postgres_repmgr_pacemaker: true
# this must be true only once, initially, when the Corosync node attributes need to be configured
# after that, repmgr will be triggering node attributes updates in case of a failover
postgres_repmgr_pacemaker_helpers_init: true
```


Running `crm_mon -AnfroRtc` will gives us the following:
```
Cluster Summary:
  * Stack: corosync
  * Current DC: repmgrpmk2 (2) (version 2.0.3-4b1f869f0f) - partition with quorum
  * Last updated: Mon Nov 16 05:53:53 2020
  * Last change:  Mon Nov 16 05:53:06 2020 by postgres via crm_attribute on repmgrpmk2
  * 3 nodes configured
  * 6 resource instances configured

Node List:
  * Node repmgrpmk1 (1): online:
    * Resources:
  * Node repmgrpmk2 (2): online:
    * Resources:
      * PostgresqlLBWriteBlock  (ocf::heartbeat:command_raw):    Started
  * Node repmgrpmk3 (3): online:
    * Resources:
      * PostgresqlLBWriteBlock  (ocf::heartbeat:command_raw):    Started

Inactive Resources:
  * Clone Set: PostgresqlLBReadBlock-clone [PostgresqlLBReadBlock]:
    * PostgresqlLBReadBlock     (ocf::heartbeat:command_raw):    Stopped
    * PostgresqlLBReadBlock     (ocf::heartbeat:command_raw):    Stopped
    * PostgresqlLBReadBlock     (ocf::heartbeat:command_raw):    Stopped
    * Stopped: [ repmgrpmk1 repmgrpmk2 repmgrpmk3 ]
  * Clone Set: PostgresqlLBWriteBlock-clone [PostgresqlLBWriteBlock]:
    * PostgresqlLBWriteBlock    (ocf::heartbeat:command_raw):    Started repmgrpmk2
    * PostgresqlLBWriteBlock    (ocf::heartbeat:command_raw):    Started repmgrpmk3
    * PostgresqlLBWriteBlock    (ocf::heartbeat:command_raw):    Stopped
    * Started: [ repmgrpmk2 repmgrpmk3 ]
    * Stopped: [ repmgrpmk1 ]

Node Attributes:
  * Node: repmgrpmk1 (1):
    * postgresql_role                   : primary   
  * Node: repmgrpmk2 (2):
    * postgresql_role                   : replica   
  * Node: repmgrpmk3 (3):
    * postgresql_role                   : replica   

Operations:
  * Node: repmgrpmk2 (2):
    * PostgresqlLBWriteBlock: migration-threshold=1000000:
      * (12) start: last-rc-change="Mon Nov 16 05:53:06 2020" last-run="Mon Nov 16 05:53:06 2020" exec-time="21ms" queue-time="0ms" rc=0 (ok)
      * (13) monitor: interval="10000ms" last-rc-change="Mon Nov 16 05:53:06 2020" exec-time="13ms" queue-time="0ms" rc=0 (ok)
  * Node: repmgrpmk1 (1):
  * Node: repmgrpmk3 (3):
    * PostgresqlLBWriteBlock: migration-threshold=1000000:
      * (12) start: last-rc-change="Mon Nov 16 05:53:06 2020" last-run="Mon Nov 16 05:53:06 2020" exec-time="28ms" queue-time="0ms" rc=0 (ok)
      * (13) monitor: interval="10000ms" last-rc-change="Mon Nov 16 05:53:06 2020" exec-time="16ms" queue-time="0ms" rc=0 (ok)
```

## Others
The role also offers the posibility to use a different/internal ip
as follows:
```yaml
group_vars:
  postgres_use_internal_ip: true
host_vars:
  node1:
    postgres_role: master
    internal_ip: 10.0.0.1
  node2:
    postgres_role: slave
    internal_ip: 10.0.0.2
  node3:
    postgres_role: slave
    internal_ip: 10.0.0.3
```

# TODO
 - integrate barman
 - add witness node configuration

## Testing

Molecule with docker is being used with 2 scenarios:
 - default - non-repmgr
 - repmgr
 - repmgr + corosync/pacemaker

Running the tests:

```bash
pipenv install
pipenv run molecule test

# or test individual scenario
# standard replication
pipenv run molecule test -s default
# repmgr managed replication and failover
pipenv run molecule test -s repmgr
# repmgr with corosync/pacemaker
pipenv run molecule test -s repmgrpmk
```

## License

MIT License

The code contains the [iptables_raw](https://github.com/Nordeus/ansible_iptables_raw) ansible module which is also licensed under MIT License.