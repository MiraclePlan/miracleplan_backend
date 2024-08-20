from sqlalchemy import Column, Integer, String, ForeignKey, Table, Date, Boolean
from sqlalchemy.orm import relationship
from database import Base

group_membership = Table('group_membership', Base.metadata,
                         Column('user_id', Integer, ForeignKey('users.id')),
                         Column('group_id', Integer, ForeignKey('groups.id'))
                         )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    # profile = Column(String(255))
    todos = relationship("Todo", back_populates="creator")
    groups = relationship("Group", secondary=group_membership, back_populates="members")


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)
    completed = Column(Boolean, default=False)
    creator_id = Column(Integer, ForeignKey('users.id'))
    creator = relationship("User", back_populates="todos")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    creator_id = Column(Integer, ForeignKey('users.id'))
    members = relationship("User", secondary=group_membership, back_populates="groups")
    creator = relationship("User", back_populates="created_groups")


User.created_groups = relationship("Group", back_populates="creator")
