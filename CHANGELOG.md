# 1.2.5 (2016-03-14)

Bug fixes:
* When doing an interactive install if the user selects WAP the wrong metadata
  type was being assigned.  This bug is fixed in this release.

# 1.2.4 (2016-02-16)

Bug fixes:

* Fixed bug where remove_user plugin failed silently if invoked while user was logged in to the VM.
* Fixed bug that kept user as ADMIN if the user was initially added as ADMIN and subsequently removed
  and added as a regular user.
  
Features:
* Updated docs to include information on setting up intrusion detection and configuring the chef client version.
* Updated docs to include the steps on setting wire logging for debugging purposes.

# 1.2.3 (2016-02-05)

Bug fixes:

* Refactored to let user pass in chef client version to be installed, which addresses FB8747.
* Reporting cleaner error messages when pulling a docker image.
* Installing xfsprogs if that file system is specified on mount.  Cleanup of format script.  Addresses FB8736
* Adding organized logging for configuration management.
* Enabled configuration of intrusion detection alert threshold.

# 1.2.2 (2016-01-26)

Bug fixes:
* Fixed bug where agent failed to unmount an encrypted volume.

# 1.2.1 (2016-01-21)

Bug fixes:
* Setting the cloud type to "Konami" was failing in the last release, this
  is fixed.

# 1.2.0 (2016-01-20)

Features:
* Install Ossec with a script instead of packaging.

Bug fixes:
* Now only showing supported clouds in interactive agent install.
* Fixed ossec parser and associated tests.
* Fixed reference to close_encrypted_device in umnount_volume plugin.
* Changed plugin.conf to allow calls to unmount and unmount_volume to succeed.
* The agent will now fetch version 12.6 of chef client.
 
# 1.1.0 (2015-11-26)

Features:
* Added the ability to send ossec alerts back to DCM.
* Adjusted the URLS to reference the new DNS names, eg:
  https://linux-stable-agent.enstratius.com
* Updated openssl to version 1.0.1p.
* Updated to python version 3.5.0.
* Added puppet and chef log information to the report tarball.
* Added support for SonarCube.
* Watchdog added as a dependency.

Bug fixes:
* Fixed stale token clean up handler. Prior to this patch the agent would
  remove the stale token but then fail while creating the exception.

# 1.0.0 (2015-10-15)

QA approved 0.13.7 for stable promotion.

# 0.13.7 (2015-10-14)

Bug fixes:
* Safely preserves the token file between upgrades.

# 0.13.6 (2015-10-12)

Bug fixes:
* Fixes FB8178 by removing files by their absolute path.

# 0.13.5 (2015-10-9)

Bug fixes:
* Clean DHCP logs in the scrubber.
* Clean all files under /dcm/logs.  This fixes FB8178 by removing rotated logs

# 0.13.4 (2015-10-6)

Bug fixes:
* FB8147.  list_devices failed on RHEL 7 due to the output from listDevices
  similar to rootfs - / - -.
* Update the installation documentation to reflect the currently supported
  clouds.
* The scrubber now logs a message when a file is not found instead of failing.
* Migrated to nose2

# 0.13.3 (2015-10-2)

Bug fixes:
* GCE now sends the correct provider ID.
* Patch the remote_tester to work with the agent manager tests again.
* Fixed the recovery script in the scrubber to not use a hard coded path
  to the private key.

# 0.13.2 (2015-09-28)

Features:
* Additional documentation for the scrubber and CA certificates.
* Added encryption to the scrubber.
* Allow the upgrade program to run as a background daemon.
* Keep track of users added to the system by the agent.
* Added the option to delete the token with the scrubber.

Bug fixes:
* Fixed a bug in reporting why failures occurred in clean_image.
* Fixed bugs in the scrubber.

# 0.13.1 (2015-09-17)

Features:
* Added documentation about the handshake and connection process.
* Allowed the user to set the certificate verifications configuration
  values.
* Adjust the configuration program to setup the agent to read system CA
  certificate files where possible.

Bug fixes:
* Stopped the scrubber program from deleting the token file.

# 0.13.0 (2015-09-11)

Features:
* Added the scrubber program for cleaning up servers before making them
  into images.

Bug fixes:
* Fixed the installer script to more properly detect the existence of the
  installed package.
* Allowed the user of the installer to force an upgrade on images that
  already have the agent installed.
* Fixed a bug the caused an error when processing a rejection message from
  the DCM handshake.

# 0.12.3 (2015-08-27)

Bug fixes:
* When a websocket connects times out from being idle the agent will
  now connect back immediately instead of backing off.
* Reset the backoff to 0 after some successful activity occurs.
* Shutdown the statistics subsystem when the agent shuts down. 

# 0.12.2 (2015-08-26)

Features:
* Added documentation for running local tests.
* Added functionality into the system stat base class.
* Moved the state machine into the events package.
* Added a direct link to force the package for upgrade tests.

Bug fixes:
* Do not allow overwrite of logging and plugin files on reconfiguration.
* Cleaned up Vagrantfile for local testing.
* Flake8 and general file cleanup including deleting files.
* Fixed the agent_exists detection and cleanup in the installer script.
* Removed the storage cloud module and the dependency on libcloud.

# 0.12.1 (2015-8-20)

Features:
* Refactored to system stats to report bytes/second.
* Reorganized and added more documentation.
* Updated the dcm-agent-add-plugin to overwrite and remove plugins.

# 0.12.0 (2015-8-4)

Features:
* Sphinx documentation.
* Added a set of system monitors to support disk io operations and byte
  counts and net io byte counts.
* Refactored the plugin system to make it more friendly for third party
  plugin developers.
* Added a user friendly upgrade tool.

Bug fixes:
* Add pypi classifier for python3, fixes FB-7588
* Tightened up the websocket state machine.  Closed a unlocked window
  between receiving a handshake and processing it as a success or failure.
* Tightened up what logs are sent back to the DCM console.
* Patched to work with the current agent manager tests.
* Cleaned up the backoff logic.

# 0.11.3 (2015-7-7)

Features:
* Added support for Digital Ocean.
* Added needed clean up for Azure images in clean_image.

# 0.11.2 (2015-6-25)

Bug Fixes:
* The symlink to dcm-agent-configure at
  /opt/dcm-agent/embedded/bin/dcm-agent-configure was added back in.
* The script logger can now handle more than 1 line this will avoid
  the pipe status 141 problem.

# 0.11.1 (2015-6-23)

Bug Fixes:
* In the previous release when then extras were installed it cause the
  logs to be owned by the root user and thus the agent would fail to
  log on start and died.  This patches fixes this.
* Fixes problems when upgrading from one version to another without
  uninstalling first.

# 0.11.0 (2015-6-18)

Features:
* Ported the agent to python 3.
* Added ossec to the extras packages for intrusion detection use on
  the agent.
* Additional tests (alert messaging, backoff, job_runner, etc).
* Added a pub/sub mechanism for a cleaner separation of concerns.

Bug Fixes:
* Add a path to gem when running puppet configuration management.
* Prevent re-copying scripts when doing a re-configure.
* Prevent clean_image from directly deleting the messaging database
  and thereby breaking communication.  Now the db is cleaned out
  via a pub/sub mechanism.
* Removed legacy configure management features.

Features:

# 0.10.0 (2015-6-2)

Features:
* Cleaning all the files in the secure directory.
* Persisting the injected ID if it is found in the environment.
* Added functionality to clean images.
* Config object now contains system sudo.
* Refactored backoff mechanism and added forced backoff.
* Bumped agent to protocol version 104.

Bug Fixes:
* Fixed how clean image reports to DCM.
* Refactored the event distribution model.
* Refactored the state machine software for general use.
* Reorganized imports and did PEP8 cleanup.
* Moved Konami to DCM.
* Allowing compression option to run script plugin.
* Fixed a security issue that could allow non-administrative users 
  with access to the server to spoof the agent connection. 

# 0.9.20 (2015-4-27)

Features:
* Added reporting of process information to the --report tool.
* Removed the konami test directory.  It is now in the DCM code base.

Bug Fixes:
* The agent_docker.sh script will no longer kill the agent for
  reconfigure if it is properly configured.  This will prevent
  the agent from restarting while in the middle of processing commands.

# 0.9.19 (2015-4-23)

Features:
* Provisioning vagrant boxes with git during local testing runs.
* Enabled CA Cert verification for agent communications.

Bug Fixes:
* Execute extras package installer method as superuser.
* Updated cloud meta data to guess correctly for Azure.
* Locked the polling condition for the stat tester.
* Pinned puppet to use only known extras installation and associated configuration file.
* Make needed directories and set username in post install step.
* Remove DCM base directory and dcm user on post removal step.

# 0.9.18 (2015-4-15)

Bug Fixes:
* Remove stale latest links in package repositories.
* Normalize the cpu stats to a value between 0 and 100.
* Run apt-get update in the installer where appropriate.

# 0.9.17 (2015-4-14)

Features:
* Added RHEL 7.1 to the supported packages.
* Added a mock system stat collector for auto-scaling tests.
* Added the python module netifaces which allows for the removal
  of a legacy script.

Bug Fixes:
* Joyent auto-detection fixed on debian 6.
* Correct the agent search extra packages search path.
* Allow the PATH env to remain after scrubbing the environment.  This
  allows the extra package to install from the agent on deb based systems.

# 0.9.16 (2015-4-7)

Features:
* Audited the logs that are sent back to DCM for clarity.
* Including boot and cloud-init logs in the report tarball.
* Added support for konami to set the docker host.

Bug Fixes:
* pep8 cleanup
* Delete the pid file when the agent is shutdown to avoid mistaken pid
  conflict on startup.
* Properly report idle time in system statistic reporter.

# 0.9.15 (2015-4-2)

Features:
* Support for RHEL 7
* Detect and reconfigure an existing agent when trying to install a new
  agent.  This will help prevent the case of having multiple agents
  running.
* Send the log level when sending logs back to DCM.
* Auto-detect Azure based on the existence of "/var/lib/waagent/ovf-env.xml"

# 0.9.14 (2015-3-31)

Features:
* Added CentOS 7.0 packages.
* Added major version only installation to the installer.  This allows
  for example Debian 7.8 to find and install Debian 7.7 packages.
* Throw a nicer error when a bad hostname is passed to rename.
* No longer alter the hostname passed to rename.

Bug Fixes:
* Fixed version detection for RHEL/CentOS.
* User insserv for starting on boot on debian systems.

# 0.9.13 (2015-3-25)

Features:
* Report an error if sudo is not found on the system.
* Added daemon logging to the init.d script.
* Added a flag to install chef-client with the agent installation.
* Added help to the installer script.
* Added support for DCM konami instances.
* Added an omnibus builder for soft dependencies.  Currently puppet is
  the only package needed.
* Added switches to the installer to download and install the extras
  packages.
* Added additional logging.
* Upgraded to SQLite 3.8
* Upgraded builder to omnibus 4.0

Bug Fixes
* Updated the certs package for curl.
* Fixed a bug prevent chef from running on RHEL
* Cleared the environment before running the agent.  This eliminated a
  problem when starting the agent with proxy variables set.
* Fixed a bug in the test suite that caused occasional "read-only DB"
  error.

# 0.9.12 (2015-1-25)

Features:
* Added a path to the agents python interpreter to the environment variable
  DCM_PYTHON in the environment in which all scripts are run.
* Added the fetch_run plug-in.  This will download a executable from a
  repository (currently just http:// and file:// are supported) and run
  it locally.
* Added support to run python scripts with the agents python interpreter
  directly.

Bug Fixes
* Fixed a problem where Joyent could not be auto-detected.
* On certain cloud and distribution combinations an agent may start before
  the meta-data server is ready.  This results in an "instance ID" of
  None and thus a failed handshake.  To fix this we get the handshake
  document with every connection attempt instead of just once at the
  beginning.  This bug occurred most often on images with "burnt-in"
  agents.

# 0.9.11 (2014-1-6)

Features:
* Support for RAID levels in addition to RAID0

Bug Fixes
* Locking in the chef version which fixes configuration management on
  ubuntu 14.04 i386.

# 0.9.10 (2014-12-19)

Bug Fixes
* Add pluginsync=true to the puppet configuration.  This fixes puppet
  on various Ubuntu 32 bit distributions.

# 0.9.9 (2014-12-17)

Features
* Removed legacy support for services and various other things that
  are not needed in the new agent.
* Removed SQL Alchemy and replaced with direct SQLite support.
* Removed references to clouds that are not yet fully supported.
* Upgrade to python 2.7.8
* pep8 cleanup of the source code.
* Do not mount if the mount point is not empty.

Bug Fixes
* Allowed default mount point to work.

# 0.9.8 (2014-12-11)

Features
* Upgraded the agent installer script to docker 1.3.2.
* Ubuntu distributions on EC2 can mount mount encrypted volumes.
* RAID mounts on Ubuntu distribution on EC2.
* Add a debug report utility so that users can more accurately
  report versions and deployments when they experience problems.

Bug Fixes
* A race condition in the jobrunner which could cause a mismatch of
  output was fixed.

# 0.9.7 (2014-12-04)

Features
* Install puppet client and DCM appropriate configuration when running
  configure_server with puppet.
* Enable mount but limit it to specific clouds and distributions.

Bug Fixes
* Decode unicode before sending log lines to DCM.
* Report errors from listDevices properly.

# 0.9.6 (2014-11-25)

Features
* Added module feature descriptors for handshake.
* Added auto-detection of platform.

Bug Fixes
* Loaded konami properly for testing support.

# 0.9.5 (2014-11-12)

Features
* Added RHEL with x86_64 and fedora as supported distributions.
* Added in initial agent support for docker.
* Added a means to guess the effective cloud that a VM is on.
* Added in support for OpenStack.
* Added script to install both the agent and docker.

Bug Fixes
* Added sudo and curl when needed in the installer script.
* Changing the default agent manager contact string and allowed
  for a default port in the url.
* Reconfiguring an agent if one was previously installed on the VM.

# 0.9.4 (2014-10-03)

Features
* Added docker plugins to allow the agent to control containers running
  via a local docker daemon.
* Enabled heartbeat from the agent to the agent manager to avoid timeouts
  from routers/firewalls/etc.
* Passed a list of available commands to the agent manager on handshake
  and thus bumped the protocol versions to 102.
* Added support module for commands that require paging.
* Improved testing code.
* Removed responses to stale lookups from the database.  This will be revisited
  in the future as the agent matures.
* Added paging support for commands with response greater than 16KB.
* Added support for CloudStack handshakes.
* Avoid the expensive "initialize" call when re-handshaking after the
  connection is dropped.
* Added a script to the archive for configuring the agent and docker from
  userdata (cloud-init style).
* Added in OpenStack meta-data allowing a successful handshake with servers
  launched on OpenStack clouds.

Bug Fixes:
* When installing if a user existed whose name contained the string "dcm"
  the install would fail.  This is now fixed.
* Repaired the install script so that the architecture can be forced as well.
* Fixed an error in the CloudStack handshake.

# 0.9.3 (2014-09-12)

Features:
* Added coverage reports for tests.
* Added vagrant tests in virtualbox to match ec2 tests.

Bug Fixes:
* Fixed a bug in type checker resulting in false successes.
* Error in installServer script fix by setting the absolute sudo path.
* Advanced to the new cacert.
* Allow the encryption key in mount to be optional.
* Fixed Azure handshake.
* Fixed GCE meta-data handshake.

# 0.9.2 (2014-08-22)

Features:
* Improved package management.
* Get DHCP address on distros that user dhcpcd.  This will allow such distros
  to work on Joyent.
* Refactored cloud meta data handling.
* Additional unit tests.
* Added auto upgrade script and confirmed upgrade behavior.

Bug Fixes:
* No longer setting the ownership of all temp files to root.
* Fixed occasional thread handler exceptions from SQLAlchemy.

# 0.9.1 (2014-08-05)

Features:
* An enhancements to the packaging system.
* Added the program dcm-agent-gen-docs to auto-generate protocol documentation
  from the source code.
* Additional tests added for failure cases of various system commands.

Bug Fixes:
* Fix issue that caused the agent to be restarted when a connection timed out.
* Verify that user names are limited to a safe character set.

Bug Fixes:

# 0.9.0 (2014-07-16)

Initial release
---------------

Features:
* A set of pluggable modules that are remotely executed via commands from DCM.
* Communicate with DCM via websockets.
* Mount and format volumes.
* Add and remove users.
* Rename hosts.
* Interaction with content management services (chef and puppet).

Know Issues:
* May require a restart after the websocket connection times out.
  https://enstratus.fogbugz.com/default.asp?4827
