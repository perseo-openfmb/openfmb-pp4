# openfmb-pp4
OpenFMb PERSEO P4 Project - dev branch

### Remove containers
>> docker stop $(docker ps -a -q)
>> docker rm $(docker ps -a -q)

### Remove images
>> docker rmi -f $(docker images -a -q)

### Remove volumes
>> docker volume prune # Only non-used volumes

### Remove all
>> docker system prune --volumes

### Check user ID
>> echo $(id -u)

### Change folder permisions
>> chown -R $USER:$USER grafana_data