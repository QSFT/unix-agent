default['s3cmd']['url'] = 'https://github.com/s3tools/s3cmd/archive/master.tar.gz'
default['s3cmd']['gpg_passphrase'] = 'abcdefgabcdefgabcdefgabcdefg'
default['s3cmd']['secret_key'] = 'aaaaaaaaaaaaaaaaaaaa'
default['s3cmd']['access_key'] = 'AAAAAAAAAAAAAAAAAAAA'
default['s3cmd']['bucket_location'] = 'US'
default['s3cmd']['encrypt'] = false
default['s3cmd']['https'] = false
default['s3cmd']['user'] = 'ubuntu'

default['dcm']['release_bucket'] = 'dcmagentunstable'
default['dcm']['cache_bucket'] = 'testvms'

default['dcm']['git_repo'] = 'git@github.com:enStratus/es-ex-pyagent.git'
default['dcm']['git_branch'] = 'master'