from pydantic import BaseModel

class map(BaseModel):
        
    s : int

    def valid(self):
        print("value should be 7") if self.s != 7 else print("Done")

    @classmethod
    def fr():
        pass



c = map(s = 8)
c.valid()