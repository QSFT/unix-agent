Linux Agent Upgrade Tool
========================

The purpose of this tool is to facilitate the upgrade of the agent so as to require as little as possible from 
the user running the upgrade.

The tool itself preserves the agent configuration values the user had previously defined in order to use
them with the newer, upgraded agent.

The tool is located within the agent repo itself as of version 0.11.3.  Go to ``dcm/agent/tests/autoupgrade``
to find the tools.  The tools will also be available in the online repos where the agent packages themselves are
found. 

There you will find the actual tool called
`upgrade.py <http://linux.development.agent.enstratius.com/upgrade.py>`_ and
a small shell wrapper for your convenience called
`upgrade.sh <http://linux.development.agent.enstratius.com/upgrade.sh>`_.

The wrapper script can accept a small number of args, only one of which is required.  Here is a description of the 
arguments you can pass::

  Usage: ./upgrade.sh version [ base_dir [ package_url [ allow_unkown_certs ]]]

          --version [VERSION]        Required and sets AGENT_VERSION env var.
          --base_dir [DIR]           Optional and sets AGENT_BASE_DIR, default is /dcm.
          --package_url [URL]        Optional and sets AGENT_BASE_URL, default is http://linux-stable-agent.enstratius.com
          --allow_unknown_certs/-Z   Optional flag to disable cert validation

``--version`` is the only required parameter and is set to the version you wish to upgrade to.

``--base_dir`` tells the upgrade tool where your dcm installation is located.  The default is /dcm.

``--package_url`` tells the upgrade tool where to download the agent installer and package from.  The default is
http://linux-stable-agent.enstratius.com.

``--allow_unknown_certs/-Z`` tells the upgrade tool to specify to the agent to ignore cert checking.  This is the one
option which will not be automatically picked up by the tool.  Starting in version 0.9.19 this was available as
an option.  If you are upgrading from an agent older than that, you may need to specify this flag if you have an
on-premise install of DCM and/or if your DCM is operating without a valid certificate.

The agent report option is invoked when the tool is started to aggregate logs and meta info about the install into a 
gzip and again after the upgrade.  In addition the upgrade tool logs to a single file while it is running.  These 
items will be copied to a temp directory for your consumption if the need arises.  You will see a message at the
finish of the upgrade telling you the location.
