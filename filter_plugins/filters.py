
from ansible.errors import AnsibleError

def filter_first_hostvars(hostvars, key, value, throw=True):
  for hostvar in hostvars.values():
    if hostvar.get(key, None) == value:
      return hostvar
  if throw:
    raise AnsibleError("Failed to find {}={} in hostvars".format(key, value))

class FilterModule(object):

    def filters(self):
        return {
            'filter_first_hostvars': filter_first_hostvars,
         }
