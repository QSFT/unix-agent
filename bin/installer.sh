#!/usr/bin/env bash
# DCM Agent Installer for Linux

SHELL_PID=$$
installer_cmd=""

function print_help() {
    echo "
This script will fetch and install the dcm-agent on the virtual machine where
it is run.  When run with no options it will detect the VM's Linux
distribution and download the appropriate stable package.  The following
environment variables will alter the behavior as described:

AGENT_LOCAL_PACKAGE=<path>
  - When set the script will look for the distribution package at the
    given path on the local file system, or the given full URL.

AGENT_BASE_URL=<url>
  - This is the base path to an HTTP repository where the packages are kept.
    For example: https://linux-development-agent.enstratius.com.  Packages will
    be found under that url with a name that matches:
    dcm-agent-<distribution>-<distribution version>-<architecture>.<pkg type>
    For example: dcm-agent-ubuntu-10.04-amd64.deb

AGENT_UNSTABLE
  - When set the script will download and install the latest unstable version
    of the dcm-agent.

AGENT_VERSION
  - To download a specific version of the agent set this to the version.

DCM_AGENT_FORCE_DISTRO_VERSION
  - Instead of detecting the distribution version force it to this env string.

DCM_AGENT_REMOVE_EXISTING
  - If this program is run on a machine that already has an agent installed
    we will remove and clean up the existing agent.

DCM_AGENT_CLEANUP
  - If an agent is already installed on the server and this is set the all
    files associated with the previous install will be removed.

###############################################################################

Optional Arguments:
  -h, --help            show this help message and exit

  --cloud {Amazon, etc...}, -c {Amazon, etc...}
                        The cloud where this virtual machine will be run.
                        Options: Amazon, Azure, CloudStack, CloudStack3,
                        Eucalyptus, Google, Joyent, OpenStack, Other, UNKNOWN

  --url URL, -u URL     The location of the dcm web socket listener

  --verbose, -v         Increase the amount of output produced by the script.

  --interactive, -i     Run an interactive session where questions will be
                        asked and answered via stdio.

  --base-path BASE_PATH, -p BASE_PATH
                        The path to enstratius

  --mount-point MOUNT_PATH, -m MOUNT_PATH
                        The path to mount point

  --on-boot, -B         Setup the agent to start when the VM boots

  --reload-conf RELOAD, -r RELOAD
                        The previous config file that will be used to populate
                        defaults.

  --temp-path TEMP_PATH, -t TEMP_PATH
                        The temp path

  --user USER, -U USER  The system user that will run the agent.

  --connection-type CON_TYPE, -C CON_TYPE
                        The type of connection that will be formed with the
                        agent manager.

  --logfile LOGFILE, -l LOGFILE

  --loglevel LOGLEVEL, -L LOGLEVEL
                        The level of logging for the agent.

  --chef-client, -o     Install chef client.

  --install-extras      Install extras package

  --extra-package-location URL,  url of extra packages to be installed.  Default is https://linux-stable-agent.enstratius.com

  --instrusion-detection-ossec, -d Flag to install and start ossec.  In addition the agent will process alerts.  Default is False

"
}


if [ $# -gt 0 ]; then
    if [[ "X$1" == "X--help" || "X$1" == "X-h" ]]; then
        print_help
        exit 1
    fi;
fi

function agent_exists() {
    $DCM_AGENT_PKG_QUERY > /dev/null
    return $?
}

function agent_running() {
    ps -u dcm
    return $?
}

function reconfig_prep() {
   echo "The existing version is"
   /opt/dcm-agent/embedded/agentve/bin/dcm-agent --version
   /etc/init.d/dcm-agent stop
   pkill -9 dcm-agent
   rm -f /dcm/secure/*
   rm -f /dcm/logs/*
}


# This will set:
#   DCM_AGENT_DISTRO_NAME
#   DCM_AGENT_DISTRO_VERSION_FULL
#   DCM_AGENT_DISTRO_VERSION_X
#   DCM_AGENT_DISTRO_VERSION_Y
#   DCM_AGENT_DISTRO_VERSION_Z
#   DCM_AGENT_DISTRO_VERSION_USED
function identify_distro_version() {

    if [ -x "/usr/bin/lsb_release" ]; then
        lsb_info=$(/usr/bin/lsb_release -i | cut -f2)
        DCM_AGENT_DISTRO_VERSION_FULL=$(/usr/bin/lsb_release -r | cut -f2)
        case $lsb_info in
            "Ubuntu")
                export DCM_AGENT_DISTRO_NAME="ubuntu"
                ;;
            "Debian")
                export DCM_AGENT_DISTRO_NAME="debian"
                ;;
            "CentOS")
                export DCM_AGENT_DISTRO_NAME="centos"
                ;;
            "RedHatEnterpriseServer")
                export DCM_AGENT_DISTRO_NAME="rhel"
                ;;
            "n/a")
                echo "Sorry we could not detect your environment"
                exit 1
                ;;
        esac
    elif [ -f "/etc/redhat-release" ]; then
        redhat_info=$(cat /etc/redhat-release)
        distro=$(echo $redhat_info | awk '{print $1}')
        case $distro in
            CentOS)
                temp_name=$(echo $redhat_info | awk '{print $3}')
                if [ "X$temp_name" == "Xrelease" ]; then
                    temp_name=$(echo $redhat_info | awk '{print $4}')
                fi
                export DCM_AGENT_DISTRO_VERSION_FULL=$temp_name
                export DCM_AGENT_DISTRO_NAME="centos"
            ;;
            Red)
                export DCM_AGENT_DISTRO_VERSION_FULL=$(echo $redhat_info | awk '{print $7}')
                export DCM_AGENT_DISTRO_NAME="rhel"
            ;;
            *)
                echo "Sorry we could not detect your environment"
                exit 1
                ;;
        esac
    elif [ -f "/etc/debian_version" ]; then
        export DCM_AGENT_DISTRO_VERSION_FULL=$(cat /etc/debian_version)
        export DCM_AGENT_DISTRO_NAME="debian"
    else
        echo "[ERROR] Unable to identify platform."
        exit 1
    fi

    export DCM_AGENT_DISTRO_VERSION_X=`echo $DCM_AGENT_DISTRO_VERSION_FULL | awk -F . '{ print $1 }'`
    export DCM_AGENT_DISTRO_VERSION_Y=`echo $DCM_AGENT_DISTRO_VERSION_FULL | awk -F . '{ print $2 }'`
    export DCM_AGENT_DISTRO_VERSION_Z=`echo $DCM_AGENT_DISTRO_VERSION_FULL | awk -F . '{ print $3 }'`

    export DCM_AGENT_DISTRO_VERSION_USED="$DCM_AGENT_DISTRO_VERSION_X.$DCM_AGENT_DISTRO_VERSION_Y"
}

# DCM_AGENT_PKG_EXTENSION
# DCM_AGENT_INSTALLER_CMD
# DCM_AGENT_REMOVE_CMD
# DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD
# DCM_AGENT_PKG_QUERY
function identify_package_installer_extension() {
    distro_name=$1

    case $distro_name in
        "ubuntu")
            export DCM_AGENT_PKG_EXTENSION="deb"
            export DCM_AGENT_INSTALLER_CMD="dpkg -i"
            export DCM_AGENT_REMOVE_CMD="dpkg -r"
            export DEBIAN_FRONTEND=noninteractive
            export DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD="apt-get install -y"
            export DCM_AGENT_PKG_QUERY="dpkg -s dcm-agent"
            apt-get update
            ;;
        "debian")
            export DCM_AGENT_PKG_EXTENSION="deb"
            export DCM_AGENT_INSTALLER_CMD="dpkg -i"
            export DCM_AGENT_REMOVE_CMD="dpkg -r"
            export DEBIAN_FRONTEND=noninteractive
            export DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD="apt-get install -y"
            export DCM_AGENT_PKG_QUERY="dpkg -s dcm-agent"
            apt-get update
            ;;
        "centos")
            export DCM_AGENT_PKG_EXTENSION="rpm"
            export DCM_AGENT_INSTALLER_CMD="rpm -Uvh"
            export DCM_AGENT_REMOVE_CMD="rpm -e"
            export DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD="yum install -y"
            export DCM_AGENT_PKG_QUERY="rpm -q dcm-agent"
            ;;
        "rhel")
            export DCM_AGENT_PKG_EXTENSION="rpm"
            export DCM_AGENT_INSTALLER_CMD="rpm -Uvh"
            export DCM_AGENT_REMOVE_CMD="rpm -e"
            export DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD="yum install -y"
            export DCM_AGENT_PKG_QUERY="rpm -q dcm-agent"
            ;;
        *)
            echo "Sorry that is not a valid distribution"
            exit 1
            ;;
    esac
}

# DCM_AGENT_ARCHITECTURE
function identify_package_architecture() {
    distro_name=$1

    tmp_bits=`uname -m`
    if [ "Xx86_64" == "X$tmp_bits" ]; then
        d=`echo $distro | sed "s/-.*//"`
        if [[ "$distro_name" == "centos" || "$distro_name" == "rhel" ]]; then
            export DCM_AGENT_ARCHITECTURE="x86_64"
        else
            export DCM_AGENT_ARCHITECTURE="amd64"
        fi
    else
        export DCM_AGENT_ARCHITECTURE="i386"
    fi
}


# Read input from terminal even if stdin is pipe.
# This function is to be used for interactive dialogue.
function read_terminal() {
    local input
    if [ -t 0 ]; then
        read input
    else
        local input_terminal=/dev/$(ps | awk '$1=='$SHELL_PID' {print $2}')
        local temp_fd_num=10
        while [ -e /dev/fd/${temp_fd_num} ]; do
            temp_fd_num=$((temp_fd_num+1))
        done
        eval "exec $temp_fd_num< $input_terminal"
        eval "read -u$temp_fd_num input"
        eval "exec $temp_fd_num<&-"
    fi
    echo $input
}


# Install agent. It downloads a distro-specific agent.
function download_agent_package {
    base_url=$1
    filename=$2
    url="$base_url/$filename"
    echo "Downloading DCM Agent from $url"
    echo "This may take a few minutes."

    export DCM_AGENT_SYSTEM_PACKAGE="/tmp/$filename"
    if [ "X$AGENT_LOCAL_PACKAGE" == "X" ]; then
        echo "Downloading $url ..."
        curl --fail -s -L $url > $DCM_AGENT_SYSTEM_PACKAGE
    else
        if [[ $AGENT_LOCAL_PACKAGE == *://* ]] ; then
            curl --fail -s -L $AGENT_LOCAL_PACKAGE > $DCM_AGENT_SYSTEM_PACKAGE
        else
            cp $AGENT_LOCAL_PACKAGE $DCM_AGENT_SYSTEM_PACKAGE
        fi
    fi
}


# Install agent. It downloads a distro-specific agent.
function install_agent(){

    echo "Installing $DCM_AGENT_SYSTEM_PACKAGE"
    if [ ! -s $DCM_AGENT_SYSTEM_PACKAGE ]; then
        echo "[ERROR] There is no local package to install.  The download failed."
        exit 1
    fi

    echo "Installing DCM Agent."
    cd /tmp

    $DCM_AGENT_INSTALLER_CMD $DCM_AGENT_SYSTEM_PACKAGE
    if [ $? -ne 0 ]; then
        echo "[ERROR] Installation failed."
        exit 1
    fi

    cd ~
    rm -f $DCM_AGENT_SYSTEM_PACKAGE 2>&1 > /dev/null
}


# Install chef-client.
function install_chef_client {
    while [[ $chef_install != "yes" && $cmd_opts_install != "yes" ]]; do
        echo -n "(Optional) Would you like to install chef client? (Y/N) "
        chef_install=$( read_terminal | tr '[:upper:]' '[:lower:]' )
        case $chef_install in
            y | yes)
                chef_install="yes"
                break;;
            n | no)
                chef_install="no"
                break;;
            *)
                chef_install="wrong";;
        esac
    done

    if [[ $chef_install == "yes" ]]; then
        echo "Installing chef-client."
        curl -L http://www.opscode.com/chef/install.sh | sudo bash -s -- -v 11.16.4
        echo "Done."
    fi
}


function handle_deps {
    which curl > /dev/null
    if [ $? -ne 0 ]; then
        $DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD curl
        if [ $? -ne 0 ]; then
            echo "curl must be installed on your system to use this installer."
            exit 1
        fi
    fi
    which sudo > /dev/null
    if [ $? -ne 0 ]; then
        $DCM_AGENT_PACKAGE_MANAGER_INSTALL_CMD sudo
        if [ $? -ne 0 ]; then
            echo "sudo must be installed on your system to use this installer."
            exit 1
        fi
    fi
}


function set_base_url {
    if [[ "X$AGENT_BASE_URL" == "X" || "X$AGENT_BASE_URL" == "XNONE" ]]; then
        if [ "X$AGENT_UNSTABLE" != "X" ]; then
            export AGENT_BASE_URL="https://linux-development-agent.enstratius.com"
        else
            export AGENT_BASE_URL="https://linux-stable-agent.enstratius.com"
        fi
    fi
}


set_base_url
identify_distro_version
identify_package_installer_extension $DCM_AGENT_DISTRO_NAME
identify_package_architecture $DCM_AGENT_DISTRO_NAME
handle_deps

agent_version_ext=""
if [ "X$AGENT_VERSION" != "X" ]; then
    agent_version_ext="-$AGENT_VERSION"
fi

if agent_running; then
    if [ -z $DCM_AGENT_REMOVE_EXISTING ]; then
        echo '******************************************************************'
        echo 'The agent is running.  Installing an agent while it is running can'
        echo 'have undefined results.  If you want to install anyway please set'
        echo 'the env DCM_AGENT_REMOVE_EXISTING=true.'
        echo '******************************************************************'
        exit 1
    fi
fi


# If the agent version is set we use only it
if [ ! -z $DCM_AGENT_FORCE_DISTRO_VERSION ]; then
    echo $DCM_AGENT_FORCE_DISTRO_VERSION
    fname="dcm-agent-$DCM_AGENT_FORCE_DISTRO_VERSION$agent_version_ext.$DCM_AGENT_PKG_EXTENSION"
    echo "Using the forced distro package $fname"
    download_agent_package $AGENT_BASE_URL $fname
else

    # first try to get the major.minor package version
    dcm_agent_distro_version=$DCM_AGENT_DISTRO_NAME-$DCM_AGENT_DISTRO_VERSION_X.$DCM_AGENT_DISTRO_VERSION_Y-$DCM_AGENT_ARCHITECTURE
    echo "Attempting to download the version for $dcm_agent_distro_version"
    fname="dcm-agent-$dcm_agent_distro_version$agent_version_ext.$DCM_AGENT_PKG_EXTENSION"
    echo "    $fname"
    download_agent_package $AGENT_BASE_URL $fname
    if [ $? -ne 0 ]; then
        echo "WARNING:  The specific version of your distribution has not been tested."
        echo "WARNING:  We will try to install the by major version only.  In most cases this will work."

        dcm_agent_distro_version=$DCM_AGENT_DISTRO_NAME-$DCM_AGENT_DISTRO_VERSION_X-$DCM_AGENT_ARCHITECTURE
        echo "Attempting to download the version for $dcm_agent_distro_version"
        fname="dcm-agent-$dcm_agent_distro_version$agent_version_ext.$DCM_AGENT_PKG_EXTENSION"
        echo "    $fname"
        download_agent_package $AGENT_BASE_URL $fname
    fi
fi
if [ $? -ne 0 ]; then
    echo "ERROR: We failed to find a package for your system"
    exit 1
fi


#
#  Here we clean up the previously installed agent if that was requested
#  explicitly.  This allows the agent to be upgraded without a deleting
#  any needed files (token) but also allows for an upgrade and reconfigure
#
if [ ! -z $DCM_AGENT_CLEANUP ]; then
    if agent_exists; then
        if agent_running; then
            echo "ERROR!  The agent previously existed and is already running."
            echo "------  This can cause token reuse in ways that will not allow"
            echo "        this agent to authenticate.  This is not supported."
            exit 1
        fi
        echo '**************************************'
        echo 'The dcm agent is already installed.'
        echo "Cleaning up the previous configuration."
        echo '**************************************'
        rm -f /dcm/logs/*
        rm -f /dcm/secure/*
    fi
fi
if agent_exists; then
    if [ -z $DCM_AGENT_REMOVE_EXISTING ]; then
        echo '**************************************'
        echo 'Python agent is already installed'
        echo 'Deleting old db and files to prepare for new configuration'
        echo '**************************************'
        if agent_running; then
            echo "ERROR!  The agent previously existed and is already running."
            echo "------  This can cause token reuse in ways that will not allow"
            echo "        this agent to authenticate.  This is not supported."
            exit 1
        fi
        reconfig_prep
    else
        if agent_running; then
            echo '**************************************'
            echo 'Stopping the agent.'
            echo '**************************************'
            /etc/init.d/dcm-agent stop
        fi
        echo '**************************************'
        echo 'Removing the existing agent.'
        echo '**************************************'
        $DCM_AGENT_REMOVE_CMD dcm-agent
        if [ $? -ne 0 ]; then
            echo "Failed to remove the existing agent!"
            exit 1
        fi

        echo '**************************************'
        echo 'Installing the agent.'
        echo '**************************************'
        install_agent
    fi
else
    echo '**************************************'
    echo 'Proceeding with installation of Agent'
    echo '**************************************'
    install_agent
fi

# Create configuration file and optionally install chef client(subject to change).
if [ "X$1" == "X" ]; then
    env -i PATH=$PATH /opt/dcm-agent/embedded/agentve/bin/dcm-agent-configure -i --base-path /dcm
    # Install optional packages.
    install_chef_client
else
    for flag in $@
      do
        case $flag in
          (--chef-client|-o)
          echo "Installing chef-client."
          curl -s -L https://www.opscode.com/chef/install.sh | bash
          echo "Done."
          ;;
          (*)
          ;;
        esac
      done
    echo /opt/dcm-agent/embedded/agentve/bin/dcm-agent-configure $@
    env -i PATH=$PATH /opt/dcm-agent/embedded/agentve/bin/dcm-agent-configure $@
fi

# Notification for non-native packages.
if [[ $platform != 'ubuntu' ]]; then
    echo "========================================================================================="
    echo "[ALERT] secure-delete was not installed since it is not natively available in ${platform}."
    echo "[ALERT] If you want to make secure-delete functional, please download and install it."
    echo "[ALERT] http://sourceforge.net/projects/srm/"
    echo "========================================================================================="
fi

rm -f /dcm/logs/*
echo "To start the agent now please run:"
echo " /etc/init.d/dcm-agent start"
