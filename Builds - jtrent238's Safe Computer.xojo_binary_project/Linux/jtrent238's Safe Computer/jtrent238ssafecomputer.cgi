#!/usr/bin/perl -w

use constant TYPE_VALUE => 0;
use constant TYPE_STRUCT => 1;
use constant MAX_CHUNK => 65000;
use constant PACK_KEY => 'V';
use strict;

my @required_modules = ('IO::Socket','File::Basename','Cwd \'abs_path\'');
our $is_windows = ($^O eq 'MSWin32');
if ($is_windows == 1) {
	@required_modules = (@required_modules,('Win32','Win32::Process','Win32::File','Socket qw(:DEFAULT :crlf)','CGI qw(:standard)'));
}
foreach (@required_modules) {
	if (lazyLoadModule($_) != 1) {
		handle_error("This script requires the $_ module.");
		exit;
	}
}
our $process_type = 0;
if ($is_windows) {
	eval '$process_type = DETACHED_PROCESS'; warn $@ if $@;
}

our $request;
our %config = load_config();
our $app_port = $config{'port'};
our $app_name = $config{'appname'};
our $app_path = script_directory() . "/" . $app_name;
if ($config{'auto_port'} eq "1") {
	$app_port = pick_port($config{'port'});
	if ($config{'port'} != $app_port) {
		$config{'port'} = $app_port;
		write_config(%config);
	}
}

cgi_handler();

exit;

sub cgi_handler {
	my $type;
	my $length = 0;
	my $response;
	my $responded = 0;
	my $sock = create_socket($app_port);
	
	if (!test_connection($sock)) {
		my $launch = launch($app_port);
		if ($launch == 1) {
			$sock = create_socket($app_port);
			if (!$sock) {
				handle_error("Application launched, but unable to connect using port $app_port.");
				exit;
			}
		} else {
			my $filename = "/tmp/$app_name";
			if(-e $filename) {
				unlink $filename;
				my $launch = launch($app_port);
				if ($launch == 1) {
					$sock = create_socket($app_port);
					if (!$sock) {
						handle_error("Mutex cleaned, application launched, but unable to connect using port $app_port.");
						exit;
					}
				} else {
					handle_error("Mutex cleaned, application could not launch.");
					exit;
				}											
			}
		}
	}
	
	my $body = "";
	if ($is_windows == 1) {
		$body .= getEnv('GATEWAY_INTERFACE');
		$body .= getEnv('HTTPS');
		$body .= getEnv('HTTP_ACCEPT');
		$body .= getEnv('HTTP_ACCEPT_ENCODING');
		$body .= getEnv('HTTP_ACCEPT_LANGUAGE');
		$body .= getEnv('HTTP_CONNECTION');
		$body .= getEnv('HTTP_HOST');
		$body .= getEnv('HTTP_REFERER');
		$body .= getEnv('HTTP_USER_AGENT');
		$body .= getEnv('REMOTE_ADDR');
		$body .= getEnv('REMOTE_HOST');
		$body .= getEnv('REQUEST_METHOD');
		$body .= getEnv('SCRIPT_NAME');
		$body .= getEnv('SERVER_NAME');
		$body .= getEnv('SERVER_PORT');
		$body .= getEnv('SERVER_PROTOCOL');
		$body .= getEnv('SERVER_SOFTWARE');
		$body .= getEnv('SERVER_URL');
		$body .= getEnv('CONTENT_LENGTH');
		$body .= getEnv('DOCUMENT_ROOT');
		$body .= getEnv('PATH_INFO');
		$body .= getEnv('PATH_TRANSLATED');
		$body .= getEnv('QUERY_STRING');
		$body .= getEnv('REDIRECT_URL');
		$body .= getEnv('REQUEST_URI');
	}
	foreach my $key (sort keys(%ENV)) {
		$body .= create_value(TYPE_VALUE,$key);
		$body .= create_value(TYPE_VALUE,$ENV{$key});
	}
	
	my $sin = "";
	if ($ENV{'REQUEST_METHOD'} eq 'POST') {
		read(STDIN, $sin, $ENV{'CONTENT_LENGTH'});
	}
	
	$body .= create_value(TYPE_VALUE,"STDIN");
	$body .= create_value(TYPE_VALUE,$sin);
	$body = create_value(TYPE_STRUCT,$body);
	
	print $sock $body;
	
	my $continue = 0;
	my $loopcount = 0;
	do {
		$sock->recv($type,1);
		$sock->recv($length,4);
		
		$type = unpack('C',$type);
		$length = unpack(PACK_KEY,$length);
		
		$response = '';
		do {
			my $chunk_size = $length - length($response);
			if ($chunk_size > MAX_CHUNK) {
				$chunk_size = MAX_CHUNK;
			}
			my $r;
			$sock->recv($r,$chunk_size);
			$response .= $r;
		} until (length($response) == $length);
		
		if ($response eq 'keepalive') {
			$continue = 1;
			$loopcount++;
		} else {
			$continue = 0;
			print STDOUT $response;
			$responded = 1;
		}
	} until ($continue == 0);
	close($sock);
	
	if ($responded == 0) {
		handle_error('Did not receive response from app');
		exit;
	}
}

sub create_value {
	my ($type,$value) = @_;
	my $len = length($value);
	
	my $t = pack('C',$type);
	my $l = pack(PACK_KEY,$len);
	return $t . $l . $value;
}

sub create_socket {
	my $port = $_[0];
	my $sock = new IO::Socket::INET(
		PeerAddr => '127.0.0.1',
		PeerPort => $port,
		Proto => 'tcp',
		Reuse => 1,
		Timeout => 2
	);
	return $sock;
}

sub launch {
	my ($port) = @_;
	
	if ($is_windows == 1) {
		my $process;
		Win32::Process::Create($process, script_directory() . "/" . $app_name,"--port=".$port,0,$process_type,".") || return 0;
	} else {
		my @args = ("$app_path","--port=$port");
		system(@args) == 0 or return 0;
	}
	sleep(1);
	
	return 1;
}

sub pick_port {
	my $port;
	my $sock;
	my $attempts = 0;
	
	$port = $_[0];
	while ($attempts < 3) {
		if ($port > 0) {
			$sock = new IO::Socket::INET (
				LocalPort => $port,
				Proto => 'tcp',
				Listen => 1,
				Reuse => 1
			);
			if ($sock) {
				close($sock);
				return $port;
			}
			
			$sock = new IO::Socket::INET(
				PeerAddr => '127.0.0.1',
				PeerPort => $port,
				Proto => 'tcp'
			);
			if ($sock) {
				if (test_connection($sock)) {
					close($sock);
					return $port;
				}
			}
			
			$attempts++;
		}
		$port = 1025 + int(rand(64510));
	}
	
	return -1;
}

sub test_connection {
	my $sock = $_[0];
	if (!$sock) {
		return 0;
	}
	my $ping = create_value(TYPE_VALUE,"1");
	print $sock $ping;
	
	my $pong;
	$sock->recv($pong,6);
	if (length($pong) != 6) {
		return 0;
	} else {
		return 1;
	}
}

sub script_directory {
	my $dir = abs_path(dirname($0));
	return $dir;
}

sub get_config_file {
	my $dir = script_directory();
	return $dir . "/config.cfg";
}

sub load_config {
	my $file = get_config_file();
	my $opened = open(CONFIGFILE,"<$file");
	if (!$opened) {
		handle_error("Cannot read config at path $file: $!");
		exit;
	}
	my %configdata = ();
	my $key, my $value;
	while (my $line = <CONFIGFILE>) {
		$line = trim($line);
		($key,$value) = split("=",$line,2);
		$key = lc($key);
		$configdata{$key} = $value;
	}
	close(CONFIGFILE);
	return %configdata;
}

sub write_config {
	my %configdata = @_;
	my $file = get_config_file();
	my $opened = open(CONFIGFILE, ">$file");
	if (!$opened) {
		handle_error("Cannot write to config at path $file. $!");
		exit;
	}
	foreach my $key (sort keys(%configdata)) {
		my $value = $configdata{$key};
		$key = uc($key);
		print CONFIGFILE "$key=$value\n";
	}
	close(CONFIGFILE);
}

sub trim($)
{
	my $string = shift;
	$string =~ s/^\s+//;
	$string =~ s/\s+$//;
	return $string;
}

sub handle_error
{
	my $error = $_[0];
	my $stream = $_[1];
	if (!$stream) {
		$stream = *STDOUT;
	}
	print $stream "Status: 200 OK\n";
	print $stream "Content-type: text/plain\n\n";
	print $stream "$error\n";
}

sub shell_escape {
	$_[0] =~ s/([\s;<>\*\|`&\$!#\(\)\[\]\{\}:'"])/\\$1/g;
	return $_[0];
}

sub getEnv {
	my $param = shift;
	if($ENV{$param}) {
		return create_value(TYPE_VALUE,$param) . create_value(TYPE_VALUE,$ENV{$param});
	} else {
		return "";
	}
}

sub lazyLoadModule {
	my $module_name = $_[0];
	my $module_available = 0;
	my $cmd = 'use ' . $module_name . '; $module_available = 1;';
	eval $cmd;
	return $module_available;
}