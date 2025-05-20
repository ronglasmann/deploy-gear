import os
import socket
import sys
import traceback
import getopt

NET_DRIVER_BRIDGE = "bridge"
NET_DRIVER_HOST = "host"
DEFAULT_NET_DRIVER = NET_DRIVER_BRIDGE


# --------------------------------------------------------------------------- #
# primary entry point
def main(action_callbacks_map: dict):
    action = None

    # initialize valid options and specified arguments
    unx_opts = "a:"
    gnu_opts = ["action="]
    args = sys.argv[1:]

    try:
        # parse command line
        arguments, values = getopt.getopt(args, unx_opts, gnu_opts)

        # evaluate given options
        for current_arg, current_value in arguments:
            if current_arg in ("-a", "--action"):
                action = current_value

        else:
            if action not in action_callbacks_map.keys():
                raise Exception(f"Invalid action: {action}")
            action_callback = action_callbacks_map[action]
            action_callback()

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        # traceback.print_stack()
        exit(1)

    exit(0)


def docker_run(app_name, app_start_cmd, docker_image_name=None, net_name=None,
               port_mappings=None, volume_mappings=None, log_group_base=None):

    if not docker_image_name:
        raise Exception(f"Unspecified docker_image_name for {app_name}")

    cmd = f"{sudo()} docker run --name {app_name} --env APP_NAME={app_name} "
    cmd += f"--env RUNTIME_ENV={environment()} --env PYTHONUNBUFFERED=1 "
    if net_name is not None:
        cmd += f"--network {net_name} "

    # expose ports
    if port_mappings and len(port_mappings) > 0:
        for pm in port_mappings:
            host_port = pm[0]
            cont_port = pm[1]
            cmd += f"-p {host_port}:{cont_port} "

    # map volumes
    if volume_mappings and len(volume_mappings) > 0:
        for vm in volume_mappings:
            host_vol = vm[0]
            cont_vol = vm[1]
            cmd += f"-v {host_vol}:{cont_vol} "

    # use the aws log driver in Test and Live so the logs go to Cloudwatch
    if environment() == ENV_TEST or environment() == ENV_LIVE:
        if not log_group_base:
            raise Exception(f"Unspecified log_group_base for the {environment()} environment")
        cmd += f"--log-driver=awslogs "
        cmd += f"--log-opt awslogs-group={log_group(log_group_base)} --log-opt awslogs-create-group=true "
        cmd += f"--log-opt awslogs-stream={app_name} "

    # in the Dev environment expect AWS keys must be set in the system environment
    if environment() == ENV_DEV:
        cmd += f"--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID "
        cmd += f"--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY "

    cmd += f"-d -i {docker_image_name} "
    cmd += f"{app_start_cmd}"

    # print(cmd)
    os.system(cmd)


def docker_stop(app_name):
    os.system(f"{sudo()} docker stop {app_name} || true")
    os.system(f"{sudo()} docker wait {app_name} || true")
    os.system(f"{sudo()} docker rm {app_name} || true")


def docker_login_ecr(the_region=None, profile=None, ecr_repo=None):
    if ecr_repo is None:
        raise Exception(f"Unspecified ecr_repo")
    if the_region is None:
        the_region = region()
    cmd = f"aws ecr get-login-password --region {the_region} "
    if profile:
        cmd += f"--profile {profile} "
    cmd += "| "
    cmd += f"{sudo()} docker login --username AWS --password-stdin {ecr_repo} "
    os.system(cmd)


def docker_pull(docker_image_name=None, docker_image_version="latest"):
    if not docker_image_name:
        raise Exception(f"Unspecified docker_image_name when pulling")
    os.system(f"{sudo()} docker pull {docker_image_name}:{docker_image_version}")


def docker_build(docker_image_name=None):
    if not docker_image_name:
        raise Exception(f"Unspecified docker_image_name when building")
    cmd = f"DOCKER_BUILDKIT=1 docker build -f Dockerfile "
    cmd += f"--build-arg AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID "
    cmd += f"--build-arg AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY "
    cmd += f"-t {docker_image_name} . "
    os.system(cmd)


def docker_prune():
    os.system(f"{sudo()} docker system prune -f")


# --------------------------------------------------------------------------- #
# docker network create
def docker_network_create(net_name=None, driver=DEFAULT_NET_DRIVER):
    if driver == NET_DRIVER_BRIDGE:
        if net_name is None:
            raise Exception(f"Unspecified net_name when creating {driver} network")
        cmd = f"{sudo()} docker network inspect {net_name} >/dev/null 2>&1 " \
              f"|| {sudo()} docker network create --driver {driver} {net_name}"
    else:
        cmd = f"{sudo()} docker network create --driver {driver} "
    os.system(cmd)


def docker_network_destroy(net_name=None):
    if net_name is None:
        raise Exception(f"Unspecified net_name when destroying network")
    os.system(f"{sudo()} docker network rm {net_name} || true")


def docker_service_start():
    os.system(f"{sudo()} service docker start || true")


def log_group(base_log_group=None):
    if base_log_group is None:
        raise Exception(f"Unspecified base_log_group")
    return f"{base_log_group}/{environment()}/{socket.gethostname()}"


# def image_name(base_image_name=IMAGE_NAME_BASE):
#     if environment() == ENV_DEV:
#         return base_image_name
#     return f"{ECR_REPO}/{base_image_name}"


# --------------------------------------------------------------------------- #
# run commands as root outside the Dev environment
def sudo():
    if environment() == ENV_DEV:
        return ""
    return "sudo"


# --------------------------------------------------------------------------- #
# runtime environments and regions
ENV_KEY = "RUNTIME_ENV"
ENV_DEV = "Dev"
ENV_TEST = "Test"
ENV_LIVE = "Live"
ENV_LIST = [ENV_DEV, ENV_TEST, ENV_LIVE]

REG_KEY = "RUNTIME_REG"
REG_ONE = "us-east-1"
REG_TWO = "us-east-2"
REG_LIST = [REG_ONE, REG_TWO]


def environment():
    if ENV_KEY not in os.environ:
        os.environ[ENV_KEY] = ENV_DEV
    env = os.environ[ENV_KEY]
    if env not in ENV_LIST:
        raise Exception(f"Unsupported environment: {env}")
    return env


def region():
    if REG_KEY not in os.environ:
        os.environ[REG_KEY] = REG_ONE
    reg = os.environ[REG_KEY]
    if reg not in REG_LIST:
        raise Exception(f"Unsupported region: {reg}")
    return reg
