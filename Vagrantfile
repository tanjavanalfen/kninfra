$sankhara_ip = '10.107.110.2'
$phassa_ip = '10.107.110.3'

POST_UP_MSG = <<-EOM
The virtual machines sankhara and phassa should be running:

   http://%{sankhara_ip}
   KN user: admin    password: %{chucknorris}

To get a shell on sankhara, run `vagrant ssh'.  On the VM, run

    `sudo systemctl restart django' after changing the site and
    `sudo salt-call state.highstate'  after changing salt config

See `salt/pillar/vagrant.sls' for other auto-generated passwords.
EOM

Vagrant.require_version ">= 1.6.0"

# Configuration of vagrant
def configure_vagrant
    Vagrant.configure(2) do |config|
        # See https://docs.vagrantup.com/v2/multi-machine/
        def common(config, hostname)
            config.vm.box = "debian/contrib-stretch64"
            config.vm.hostname = "vagrant-" + hostname + ".lan"
            config.vm.synced_folder "salt/states", "/srv/salt", \
                                    type: "virtualbox"
            config.vm.synced_folder "salt/pillar", "/srv/pillar", \
                                    type: "virtualbox"
            config.vm.synced_folder ".", "/vagrant", type: "virtualbox"
            config.vm.provision :salt do |salt|
                salt.run_highstate = true
                salt.verbose = true
                salt.minion_config = "salt/vagrant_minion_config"

                # Workaround for mitchellh/vagrant#5973,
                # see https://github.com/mitchellh/vagrant/issues/5973#issuecomment-137276605
                salt.bootstrap_options = "-F -c /tmp/ -P"
            end

            config.vm.provider "virtualbox" do |v|
                # Work-around symlink problem in windows.
                # See http://stackoverflow.com/questions/24200333/symbolic-links-and-synced-folders-in-vagrant
                if Vagrant::Util::Platform.windows?
                    v.customize ["setextradata", :id,
                        "VBoxInternal2/SharedFoldersEnableSymlinksCreate/v-root",
                                                                        "1"]
                end

                # http://serverfault.com/questions/453185/
                v.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
            end
        end

        int = public_interface

        config.vm.define "phassa" do |config|
            common config, "phassa"
            config.vm.network :public_network, :bridge => int if int
            config.vm.network :private_network, ip: $phassa_ip
        end

        config.vm.define "sankhara", primary: true do |config|
            common config, "sankhara"
            config.vm.network :public_network, :bridge => int if int
            config.vm.network :private_network, ip: $sankhara_ip

            config.vm.post_up_message = POST_UP_MSG % {
                        sankhara_ip: $sankhara_ip,
                        chucknorris: vagrant_pillar['secrets']['chucknorris'] }
        end

        # vagrant plugin install vagrant-cachier
        if Vagrant.has_plugin? "vagrant-cachier"
            config.cache.scope = :box
        end
    end
end

# Helpers (eg. generating passwords)
require 'yaml'
require 'securerandom'

def vagrant_pillar
    return YAML.load_file(vagrant_pillar_path)
end

def vagrant_pillar_path
    return File.join(File.dirname(__FILE__), 'salt', 'pillar', 'vagrant.sls')
end

def ensure_pillar_is_generated
    names = ['chucknorris', 'django_secret_key', 'apikey', 'mysql_giedo',
                'mysql_wiki', 'mysql_wolk', 'mysql_root',
                'mysql_daan', 'mailman_default', 'ldap_infra', 'mysql_piwik',
                'ldap_daan', 'ldap_freeradius', 'ldap_admin',
                'ldap_saslauthd', 'wiki_key', 'wiki_upgrade_key',
                'wiki_admin' ]

    path = vagrant_pillar_path
    return if File.exists?(path) and File.mtime(path) >= File.mtime(__FILE__)

    puts 'Generating passwords ...'
    if File.exists? path
        pillar = YAML.load_file(path)
    else
        pillar = {'secrets' => {}}
    end

    # Generate secrets
    for name in names
        next if pillar['secrets'].include? name
        pillar['secrets'][name] = SecureRandom.hex
    end

    # Some other settings
    pillar['ldap-suffix'] = 'dc=vagrant-sankhara,dc=lan'
    pillar['ip-phassa'] = $phassa_ip
    pillar['ip-sankhara'] = $sankhara_ip

    pillar['python3'] = false unless pillar.include? 'python3'

    File.open(path, 'w') do |f|
        f.write "# autogenerated by Vagrantfile"
        YAML.dump pillar, f
    end
end

def public_interface
    path = File.join(File.dirname(__FILE__), '.vagrant-network-interface')
    return false unless File.exists? path
    return File.open(path).read.strip
end

def check_environment
    if Vagrant::Util::Platform.windows?
        require 'win32/registry'
        def elevated?
            begin
                Win32::Registry::HKEY_USERS.open('S-1-5-19') { | reg | }
                return true
            rescue
            end
            return false
        end

        if not elevated?
            puts
            puts
            puts "On Windows, vagrant needs to be run with administrative"
            puts "privileges.  Otherwise symlinks will not work."
            puts "See http://stackoverflow.com/questions/24200333/symbolic-links-and-synced-folders-in-vagrant"
            puts
            puts "   sorry..."
            exit -1
        end
    end
end

check_environment
ensure_pillar_is_generated
configure_vagrant

# vi: set ft=ruby :
